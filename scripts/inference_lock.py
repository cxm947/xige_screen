"""Keep this user's local model jobs from exhausting memory through concurrency."""
from contextlib import contextmanager
import os
from pathlib import Path
from redub_core import fail


def default_lock_path():
    # Per-user location remains the same when an agent gives each job its own TEMP.
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))
    else:
        base = os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))
    return Path(base) / 'xige_screen/inference.lock'


@contextmanager
def inference_lock(path=None):
    path = Path(path) if path else default_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    with path.open('r+b') as stream:
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                fail('INFERENCE_BUSY', 'Another xige_screen model job is running. Wait for that process; do not start a second inference job.')
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                fail('INFERENCE_BUSY', 'Another xige_screen model job is running. Wait for that process.')
        try:
            stream.seek(0)
            stream.write(str(os.getpid()).encode('ascii'))
            stream.truncate(); stream.flush()
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
