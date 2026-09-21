#!/usr/bin/env python3
"""Entry point for the installed Windows runtime; no system Python needed."""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent


def configure(root):
    import imageio_ffmpeg
    root = Path(root)
    ff = root / 'tools/ffmpeg.exe'
    if not ff.exists():
        ff.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), ff)
    os.environ['REDUB_FFMPEG'] = str(ff)
    os.environ['PATH'] = str(ff.parent) + os.pathsep + os.environ.get('PATH', '')
    os.environ['PYTHONUTF8'] = '1'
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONNOUSERSITE'] = '1'
    os.environ['PYTHONUNBUFFERED'] = '1'
    os.environ['HF_HOME'] = str(root / 'cache/huggingface')
    os.environ['MPLCONFIGDIR'] = str(root / 'cache/matplotlib')
    os.environ['NUMBA_CACHE_DIR'] = str(root / 'cache/numba')
    return ff


def run(argv):
    return subprocess.run([str(x) for x in argv], check=True)


def doctor(root):
    from windows_compat import enable_windows_fst_paths
    enable_windows_fst_paths()
    from wetext import Normalizer
    if not Normalizer(lang='zh').normalize('安装测试123'):
        raise RuntimeError('Text normalizer returned empty output')
    import torch
    from redub_media import ffmpeg_path, ff_version
    config = json.loads((root / 'backend.json').read_text(encoding='utf-8'))
    sys.path.insert(0, config['repo'])
    from indextts.infer_v2_5 import IndexTTS2  # Verify actual import chain, not just installed package names.
    from indextts.s2mel.modules.length_regulator import InterpolateRegulator  # Loaded lazily by model construction.
    if config['device'].startswith('cuda'):
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA driver is not usable. Update the NVIDIA driver or rerun Install.cmd -Device cpu.')
        test = torch.ones((32, 32), device=config['device'])
        if (test @ test).sum().item() != 32768:
            raise RuntimeError('CUDA computation check failed')
    report = {'python': sys.version.split()[0], 'executable': sys.executable, 'torch': torch.__version__,
              'device': config['device'], 'engine_import': IndexTTS2.__name__, 'ffmpeg': ff_version(ffmpeg_path(None)),
              'model_dir': config['model_dir'], 'cuda_available': torch.cuda.is_available()}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def make_system_reference(path):
    """Use an installed Windows system voice for engineering checks, no downloaded actor samples."""
    literal = str(path).replace("'", "''")
    command = """$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
Add-Type -AssemblyName System.Speech
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$english = $voice.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'en-*' } | Select-Object -First 1
if ($english) { $voice.SelectVoice($english.VoiceInfo.Name) }
$voice.SetOutputToWaveFile('""" + literal + """')
$voice.Speak('Welcome to the local voice test. This reference is spoken by the Windows system voice. We will now speak an entirely new sentence.')
$voice.Dispose()
"""
    encoded = base64.b64encode(command.encode('utf-16le')).decode('ascii')
    run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded])


def self_test(root):
    """Run the same ledger -> Index adapter -> compositor path as a real scene."""
    from redub_core import init_project, import_asset, atomic_json, review
    from redub_media import run as media_run, wav_write, audio_metrics, decode, render
    import numpy as np
    ff = configure(root)
    folder = root / 'checks' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    ref = folder / 'reference.wav'
    make_system_reference(ref)
    p = init_project(folder / 'project', 'synthetic://windows-install-test', 'Real model installation check; system voice reference, synthetic picture')
    project = folder / 'project'
    rate = p['settings']['sample_rate']
    # Generous slots isolate installation functionality from editorial pacing.
    media_run([ff, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=0x243344:s=640x360:r=25:d=12',
               '-f', 'lavfi', '-i', 'anullsrc=r=24000:cl=mono', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-t', '12', folder / 'source.mp4'])
    sid = import_asset(project, p, folder / 'source.mp4', 'video', 'Synthetic installation check picture')
    wav_write(folder / 'bed.wav', np.zeros(rate * 12, dtype=np.float32), rate)
    bid = import_asset(project, p, folder / 'bed.wav', 'bed', 'Deliberately silent synthetic bed')
    rid = import_asset(project, p, ref, 'reference', 'Windows installed system speech, generated for installation check')
    p['source'] = {'asset': sid, 'duration': 12.0}
    p['scene'] = {'keep': [{'start': 0, 'end': 12}], 'evidence': {'opening': 'Generated first frame', 'ending': 'Generated 12 second end', 'completeness': 'Synthetic fixture, exact duration'}}
    p['speakers'] = {'system': {'label': 'Windows system reference', 'timbre_asset': rid}}
    p['mix']['bed_asset'] = bid
    p['render']['label'] = 'LOCAL VOICE ENGINE TEST'
    p['render']['font'] = 'Arial'
    p['turns'] = [{'id': 'test_001', 'speaker': 'system', 'start': .5, 'end': 11.5,
                  'source_text': 'Windows system reference', 'text': 'The local voice engine is ready. This is a new sentence.',
                  'tts_text': 'The local voice engine is ready. This is a new sentence.', 'action': 'generate',
                  'cast_evidence': 'Single synthetic system voice, no real actor', 'performance_asset': rid,
                  'delivery': 'Neutral installation check', 'beat': 'Confirm installation', 'claim_ids': [], 'captions': []}]
    atomic_json(project / 'project.json', p)
    config = json.loads((root / 'backend.json').read_text(encoding='utf-8'))
    config['lang'] = 'EN'
    atomic_json(folder / 'backend.json', config)
    started = time.monotonic()
    run([sys.executable, HERE / 'index_adapter.py', project, '--config', folder / 'backend.json', '--turn', 'test_001', '--select'])
    p = json.loads((project / 'project.json').read_text(encoding='utf-8'))
    review(project, p, 'source', 'agent', 'Synthetic bounds known by construction', 'scripts/windows_run.py:self_test')
    review(project, p, 'script', 'agent', 'Installation engineering fixture; acting quality not evaluated', 'scripts/windows_run.py:self_test')
    result = render(project, p, str(ff))
    atomic_json(root / 'checks/latest.json', {'status': 'passed', 'kind': 'real-IndexTTS-generation-and-MP4-render',
                'project': str(project), 'elapsed_seconds': round(time.monotonic()-started, 2), 'render': result,
                'performance_auditioned': False})
    print(json.dumps({'self_test': 'passed', 'result': result, 'report': str(root / 'checks/latest.json')}, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', required=True)
    ap.add_argument('command', nargs='?', choices=['doctor', 'self-test', 'core', 'generate', 'prepare', 'transcribe', 'python'])
    ap.add_argument('arguments', nargs=argparse.REMAINDER)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    configure(root)
    if args.command is None:
        print('xige_screen is installed at ' + str(root))
        print('ChatGPT desktop local Work / Codex: select scene-redub and provide a video link + theme.')
        print('Run.cmd doctor                   Check runtime')
        print('Run.cmd self-test                Generate real speech and an MP4')
        print('Run.cmd core --help              Source, project, render and validation tools')
        print('Run.cmd generate PROJECT --turn ID --select')
        print('Run.cmd transcribe FILE --language zh --model small --word_timestamps True')
        print('For local execution, the desktop assistant needs permission to read files and run local tools.')
        return
    if args.command == 'doctor':
        doctor(root)
    elif args.command == 'self-test':
        self_test(root)
    elif args.command == 'core':
        run([sys.executable, HERE / 'redub.py', *args.arguments])
    elif args.command == 'generate':
        run([sys.executable, HERE / 'index_adapter.py', *args.arguments, '--config', root / 'backend.json'])
    elif args.command == 'prepare':
        run([sys.executable, HERE / 'prepare_scene.py', *args.arguments])
    elif args.command == 'transcribe':
        from inference_lock import inference_lock
        with inference_lock():
            run([sys.executable, '-m', 'whisper', *args.arguments, '--model_dir', root / 'models/whisper'])
    elif args.command == 'python':
        run([sys.executable, *args.arguments])


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print('RUNTIME FAILED: ' + str(exc), file=sys.stderr)
        sys.exit(1)
