from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from inference_lock import inference_lock


class InferenceLockTests(unittest.TestCase):
    def test_isolated_temp_directories_share_user_inference_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            other_temp = Path(tmp) / 'isolated-temp'
            other_temp.mkdir()
            user_cache = str(Path(tmp) / 'user-cache')
            code = 'import sys;sys.path.insert(0,sys.argv[1]);from inference_lock import inference_lock\nwith inference_lock():print("acquired")'
            with patch.dict(os.environ, {'LOCALAPPDATA':user_cache, 'XDG_CACHE_HOME':user_cache}):
                child_env = dict(os.environ, TEMP=str(other_temp), TMP=str(other_temp), TMPDIR=str(other_temp))
                with inference_lock():
                    blocked = subprocess.run([sys.executable, '-c', code, str(SCRIPTS)],
                                             env=child_env, capture_output=True, text=True)
                    self.assertNotEqual(blocked.returncode, 0)
                    self.assertIn('Another xige_screen model job', blocked.stderr)

    def test_second_process_blocked_then_can_run_after_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'inference.lock'
            code = 'import sys;sys.path.insert(0,sys.argv[1]);from inference_lock import inference_lock\nwith inference_lock(sys.argv[2]):print("acquired")'
            def child():
                return subprocess.run([sys.executable, '-c', code, str(SCRIPTS), str(path)], capture_output=True, text=True)
            with inference_lock(path):
                blocked = child()
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn('Another xige_screen model job', blocked.stderr)
            allowed = child()
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            self.assertIn('acquired', allowed.stdout)


if __name__ == '__main__':
    unittest.main()
