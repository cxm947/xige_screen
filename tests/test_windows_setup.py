from pathlib import Path
import hashlib
import http.server
import io
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from windows_setup import download, safe_extract, copy_skill, choose_device


class SetupTests(unittest.TestCase):
    def test_auto_device_uses_available_memory_not_only_gpu_name(self):
        import subprocess
        with patch('windows_setup.shutil.which', return_value='nvidia-smi'), patch('windows_setup.subprocess.run',
                return_value=subprocess.CompletedProcess([], 0, '16303, 9000\n')):
            with patch('windows_setup.available_commit', return_value=15*1024**3):
                self.assertEqual(choose_device('auto'), 'cpu')
            with patch('windows_setup.available_commit', return_value=24*1024**3):
                self.assertEqual(choose_device('auto'), 'cuda')
        self.assertEqual(choose_device('cpu'), 'cpu')
        self.assertEqual(choose_device('cuda'), 'cuda')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()

    def test_archive_cannot_escape_install_root(self):
        path = self.root / 'bad.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('release/../../escaped.txt', 'escape')
        with self.assertRaises(ValueError):
            safe_extract(path, self.root / 'dest', 'release/')
        self.assertFalse((self.root / 'escaped.txt').exists())

    def test_archive_rejects_symlinks(self):
        path = self.root / 'link.zip'
        with zipfile.ZipFile(path, 'w') as z:
            info = zipfile.ZipInfo('release/link')
            info.external_attr = 0o120777 << 16
            z.writestr(info, '../../outside')
        with self.assertRaises(ValueError):
            safe_extract(path, self.root / 'dest', 'release/')

    def test_retry_restores_partial_source_tree(self):
        path = self.root / 'good.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('release/engine/a.py', 'complete')
            z.writestr('release/engine/b.py', 'complete too')
        dest = self.root / 'dest'
        (dest / 'engine').mkdir(parents=True)
        (dest / 'engine/a.py').write_text('truncated')
        safe_extract(path, dest, 'release/')
        self.assertEqual((dest / 'engine/a.py').read_text(), 'complete')
        self.assertTrue((dest / 'engine/b.py').exists())

    def test_resume_when_server_honors_or_ignores_range(self):
        payload = b'actual downloaded model bytes' * 4096
        digest = hashlib.sha256(payload).hexdigest()
        for honor in (True, False):
            with self.subTest(honor_range=honor):
                seen = []
                class Handler(http.server.BaseHTTPRequestHandler):
                    def do_GET(self):
                        value = self.headers.get('Range')
                        seen.append(value)
                        offset = int(value.removeprefix('bytes=').split('-')[0]) if value and honor else 0
                        self.send_response(206 if offset else 200)
                        self.send_header('Content-Length', str(len(payload) - offset))
                        if offset:
                            self.send_header('Content-Range', f'bytes {offset}-{len(payload)-1}/{len(payload)}')
                        self.end_headers(); self.wfile.write(payload[offset:])
                    def log_message(self, *args):
                        pass
                server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
                try:
                    dest = self.root / (str(honor) + '.bin')
                    dest.with_name(dest.name + '.part').write_bytes(payload[:8192])
                    download([f'http://127.0.0.1:{server.server_port}/model'], dest, digest, len(payload))
                    self.assertEqual(dest.read_bytes(), payload)
                    self.assertEqual(seen, ['bytes=8192-'])
                    # A verified file is reused without further network traffic.
                    download(['http://127.0.0.1:1/unavailable'], dest, digest, len(payload))
                finally:
                    server.shutdown(); server.server_close(); thread.join()

    def test_skill_install_excludes_checkout_and_private_locator(self):
        package = self.root / 'package'; package.mkdir()
        (package / 'SKILL.md').write_text('skill')
        (package / 'runtime.json').write_text('private path')
        (package / '.git').mkdir(); (package / '.git/config').write_text('private remote')
        (package / 'Install.cmd').write_text('installer')
        (package / 'scripts').mkdir(); (package / 'scripts/setup.ps1').write_text('setup')
        dest = self.root / 'installed'
        copy_skill(package, dest)
        self.assertTrue((dest / 'SKILL.md').exists())
        self.assertTrue((dest / 'Install.cmd').exists())
        self.assertTrue((dest / 'scripts/setup.ps1').exists())
        self.assertFalse((dest / '.git').exists())
        self.assertFalse((dest / 'runtime.json').exists())


if __name__ == '__main__':
    unittest.main()
