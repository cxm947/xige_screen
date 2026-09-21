"""Process-local compatibility for the pinned Windows speech dependencies."""
import os
from pathlib import Path


def enable_windows_weight_reads():
    """Avoid Windows mapped-storage access violations when Transformers slices weights.

    Use the upstream SafeTensors positional-read backend, preserving tensors and
    metadata. This is process-local and applies before Transformers imports it.
    """
    if os.name != 'nt':
        return
    import functools
    import safetensors
    if not isinstance(safetensors.safe_open, functools.partial):
        safetensors.safe_open = functools.partial(safetensors.safe_open, backend='pread')


def enable_windows_fst_paths():
    """kaldifst uses narrow C++ filenames; load ASCII relative paths from a Unicode cwd.

    Python changes the directory with the wide Windows API. FST construction is
    synchronous and completes before generation; no installed package is edited.
    """
    if os.name != 'nt':
        return
    import wetext.wetext as wetext_module
    from kaldifst import TextNormalizer
    fst_root = Path(wetext_module.__file__).parent / 'fsts'

    def load_fst(relative):
        previous = Path.cwd()
        try:
            os.chdir(fst_root)
            return TextNormalizer(str(relative))
        finally:
            os.chdir(previous)

    wetext_module.load_fst = load_fst
