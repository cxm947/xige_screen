#!/usr/bin/env python3
"""Install the pinned Windows inference runtime; invoked by Install.cmd."""
from __future__ import annotations
import argparse
import concurrent.futures
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import threading
import urllib.request
import zipfile

INDEX_COMMIT = 'ee40fa7d6c6b8a2c7f06105f9f1e65775b74868c'
INDEX_SHA256 = 'a0e2c53621b090e142faee23e6815b9074548cffca2ff13d036a7025f6285468'


class Tee:
    def __init__(self, console, logfile):
        self.console, self.logfile = console, logfile
        self.lock = threading.Lock()
    def write(self, text):
        with self.lock:
            self.console.write(text)
            self.logfile.write(text)
            self.logfile.flush()
        return len(text)
    def flush(self):
        self.console.flush()
        self.logfile.flush()


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def download(urls, dest, expected_hash, size=None):
    """Resume only bytes of the same pinned content; verify before promotion."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and (size is None or dest.stat().st_size == size) and sha256(dest) == expected_hash:
        print('Verified: ' + dest.name, flush=True)
        return dest
    partial = dest.with_name(dest.name + '.part')
    error = None
    for attempt in range(6):
        url = urls[attempt % len(urls)]
        offset = partial.stat().st_size if partial.exists() else 0
        if size and offset >= size:
            if offset == size and sha256(partial) == expected_hash:
                partial.replace(dest)
                return dest
            partial.unlink()
            offset = 0
        headers = {'User-Agent': 'xige_screen/0.3.0', 'Accept-Encoding': 'identity'}
        if offset:
            headers['Range'] = f'bytes={offset}-'
        try:
            print(f'Downloading {dest.name} (resume {offset // 1048576} MiB)', flush=True)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as response:
                if offset and response.status != 206:
                    offset = 0
                if response.status == 206 and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                    raise ValueError('Invalid Content-Range')
                last_report = time.monotonic()
                count = offset
                with partial.open('ab' if offset else 'wb') as f:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        count += len(chunk)
                        if size and count > size:
                            raise ValueError('Downloaded content exceeds locked file size')
                        if time.monotonic() - last_report >= 10:
                            print(f'  {dest.name}: {count // 1048576} / {(size or count) // 1048576} MiB', flush=True)
                            last_report = time.monotonic()
            if size and partial.stat().st_size != size:
                raise OSError(f'Incomplete download: {partial.stat().st_size}/{size}')
            if sha256(partial) != expected_hash:
                partial.unlink()
                raise ValueError('SHA-256 mismatch')
            partial.replace(dest)
            return dest
        except (OSError, ValueError) as exc:
            error = exc
            print(f'Retry {attempt + 1}/6 for {dest.name}: {exc}', flush=True)
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f'Download failed for {dest.name}: {error}. Run Install.cmd again to resume.')


def safe_extract(archive, dest, prefix=''):
    dest = Path(dest).resolve()
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            if not entry.filename.startswith(prefix):
                raise ValueError('Unexpected archive root')
            rel = entry.filename[len(prefix):]
            if not rel:
                continue
            path = (dest / rel).resolve()
            if not path.is_relative_to(dest) or ((entry.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError('Unsafe archive member')
            if entry.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with z.open(entry) as source, path.open('wb') as target:
                    shutil.copyfileobj(source, target)


def run(args, **kwargs):
    print('Running: ' + ' '.join(str(v) for v in args), flush=True)
    process = subprocess.Popen([str(v) for v in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               encoding='utf-8', errors='replace', **kwargs)
    for line in process.stdout:
        print(line, end='', flush=True)
    if process.wait():
        raise subprocess.CalledProcessError(process.returncode, args)


@contextlib.contextmanager
def install_lock(root):
    # OS releases this byte-range lock after a crash; stale marker files are harmless.
    import msvcrt
    path = Path(root) / 'install.lock'
    with path.open('a+b') as stream:
        stream.seek(0)
        if not stream.read(1):
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError('Another xige_screen installation is still running.') from exc
        try:
            yield
        finally:
            stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def available_commit():
    """Windows GPU allocations also consume system commit, beyond physical VRAM."""
    if os.name != 'nt':
        return None
    import ctypes
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in ('total_physical', 'free_physical', 'total_commit',
                'free_commit', 'total_virtual', 'free_virtual', 'free_extended')]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return status.free_commit


def choose_device(requested):
    if requested != 'auto':
        return requested
    smi = shutil.which('nvidia-smi')
    if smi:
        p = subprocess.run([smi, '--query-gpu=memory.total,memory.free', '--format=csv,noheader,nounits'], capture_output=True, text=True)
        if p.returncode == 0:
            for line in p.stdout.splitlines()[:1]:  # The generated config uses CUDA device 0.
                try:
                    total, free = [int(v.strip()) for v in line.split(',')]
                    commit = available_commit()
                    if total >= 10000 and free >= 8000 and (commit is None or commit >= 20 * 1024**3):
                        return 'cuda'
                    print('Available GPU / system memory is limited; selecting the CPU runtime automatically.', flush=True)
                except ValueError:
                    pass
    return 'cpu'


def copy_skill(package, dest):
    from package_release import ROOT_FILES, OPTIONAL_ROOT_FILES, ROOT_DIRS, EXTS
    package, dest = Path(package).resolve(), Path(dest).resolve()
    if package == dest:
        return
    if dest.exists() and not (dest / 'SKILL.md').is_file():
        raise RuntimeError(f'Not a skill directory, refusing to overwrite: {dest}')
    dest.mkdir(parents=True, exist_ok=True)
    for path in package.rglob('*'):
        rel = path.relative_to(package)
        if '.git' in rel.parts or '__pycache__' in rel.parts:
            continue
        if path.is_symlink():
            raise ValueError('Skill package contains a symlink')
        if not path.is_file():
            continue
        if (len(rel.parts) == 1 and rel.name in ROOT_FILES | OPTIONAL_ROOT_FILES | {'release_manifest.json'}) or (len(rel.parts) > 1 and rel.parts[0] in ROOT_DIRS and path.suffix in EXTS):
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', required=True); ap.add_argument('--package', required=True)
    ap.add_argument('--device', choices=['auto', 'cuda', 'cpu'], default='auto')
    ap.add_argument('--model-cache'); ap.add_argument('--skill-dir')
    ap.add_argument('--no-skill-install', action='store_true')
    ap.add_argument('--skip-voice-test', action='store_true')
    args = ap.parse_args()
    root, package = Path(args.root).resolve(), Path(args.package).resolve()
    (root / 'logs').mkdir(parents=True, exist_ok=True)
    logfile = (root / 'logs/install-python.log').open('a', encoding='utf-8', buffering=1)
    sys.stdout = Tee(sys.stdout, logfile)
    sys.stderr = Tee(sys.stderr, logfile)
    uv, py = root / 'tools/uv.exe', root / 'env/Scripts/python.exe'
    with install_lock(root):
        device = choose_device(args.device)
        print(f'[3/5] Installing inference libraries ({device})...', flush=True)
        variant = 'cu128' if device == 'cuda' else 'cpu'
        run([uv, 'pip', 'install', '--python', py, 'torch==2.8.0+' + variant, 'torchaudio==2.8.0+' + variant,
             '--index-url', 'https://download.pytorch.org/whl/' + variant])
        run([uv, 'pip', 'install', '--python', py, '-r', package / 'requirements-windows.lock.txt'])
        if device == 'cuda':
            info = json.loads(subprocess.check_output([str(py), '-c',
                'import json,torch; print(json.dumps({"cuda":torch.cuda.is_available(), "bf16":torch.cuda.is_available() and torch.cuda.is_bf16_supported()}))'], text=True))
            if not (info['cuda'] and info['bf16']):
                if args.device == 'cuda':
                    raise RuntimeError('The CUDA driver / GPU does not support the tested BF16 backend. Update the driver or use -Device cpu.')
                print('GPU does not support this BF16 backend; selecting CPU automatically.', flush=True)
                device = 'cpu'
                run([uv, 'pip', 'install', '--python', py, 'torch==2.8.0+cpu', 'torchaudio==2.8.0+cpu',
                     '--index-url', 'https://download.pytorch.org/whl/cpu'])
        archive = download(['https://codeload.github.com/index-tts/index-tts/zip/' + INDEX_COMMIT], root / 'download-cache/index-source.zip', INDEX_SHA256, 35993020)
        repo = root / 'engine' / INDEX_COMMIT
        safe_extract(archive, repo, 'index-tts-' + INDEX_COMMIT + '/')
        print('[4/5] Downloading and verifying all model weights...', flush=True)
        manifest = json.loads((package / 'assets/models.lock.json').read_text(encoding='utf-8'))
        models = Path(args.model_cache).resolve() if args.model_cache else root / 'models/IndexTTS-2.5'
        models.mkdir(parents=True, exist_ok=True)
        needed = sum(e['bytes'] for e in manifest['files'] if not (models / e['path']).is_file())
        if shutil.disk_usage(models).free < needed + 1024 ** 3:
            raise RuntimeError(f'Insufficient disk space for model download ({needed / 1024**3:.1f} GB plus working space required).')
        def fetch(entry):
            return download(entry['urls'], models / entry['path'], entry['sha256'], entry['bytes'])
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(fetch, manifest['files']))
        config = {'repo': str(repo), 'model_dir': str(models), 'device': 'cuda:0' if device == 'cuda' else 'cpu',
                  'use_bf16': device == 'cuda', 'cpu_threads': min(8, os.cpu_count() or 4), 'lang': 'ZH'}
        atomic_json(root / 'backend.json', config)
        installed = root / 'skill/scene-redub'
        copy_skill(package, installed)
        atomic_json(installed / 'runtime.json', {'root': str(root)})
        # Write a locator into the unpacked distribution too, so Run.cmd works with a custom root.
        atomic_json(package / 'runtime.json', {'root': str(root)})
        print('[5/5] Checking engine and generating real speech...', flush=True)
        run([py, installed / 'scripts/windows_run.py', '--root', root, 'doctor'])
        if not args.skip_voice_test:
            run([py, installed / 'scripts/windows_run.py', '--root', root, 'self-test'])
        skill_dir = None
        if not args.no_skill_install:
            if args.skill_dir:
                skill_dir = Path(args.skill_dir).expanduser().resolve()
            else:
                legacy = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'skills/scene-redub'
                skill_dir = legacy if legacy.exists() else Path.home() / '.agents/skills/scene-redub'
            copy_skill(installed, skill_dir)
            atomic_json(skill_dir / 'runtime.json', {'root': str(root)})
        freeze = subprocess.check_output([str(uv), 'pip', 'freeze', '--python', str(py)], text=True)
        (root / 'logs/installed-packages.txt').write_text(freeze, encoding='utf-8')
        atomic_json(root / 'installation.json', {'version': '0.3.0', 'root': str(root), 'python': str(py), 'device': device,
                    'source_commit': INDEX_COMMIT, 'models': manifest['repositories'], 'skill': str(skill_dir) if skill_dir else None,
                    'voice_test': 'skipped' if args.skip_voice_test else 'passed', 'installed_at': time.time()})
        print('Ready. Skill: ' + str(skill_dir or installed), flush=True)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('INSTALLATION FAILED: ' + str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
