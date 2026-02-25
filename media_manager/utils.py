# Shared helpers used across the whole package: timing, filenames, yes/no prompts.

import os
import logging
import shutil
import time
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ffmpeg location
# ---------------------------------------------------------------------------
# Starts empty, which means "look for 'ffmpeg' on the system PATH".
# Call set_ffmpeg_path() at startup (CLI or GUI) once you know the user's
# preferred executable location.  Every subprocess call in the package goes
# through get_ffmpeg() so only this one place needs updating.

_ffmpeg_path: str = ""


def set_ffmpeg_path(path: str) -> None:
    """Store the user-configured ffmpeg executable path.

    Also updates MoviePy's internal ffmpeg path so that write_videofile() and
    other MoviePy calls use the same executable as our direct subprocess calls.
    Pass an empty string (or None) to fall back to 'ffmpeg' on PATH.
    """
    global _ffmpeg_path
    _ffmpeg_path = (path or "").strip()

    # Keep MoviePy in sync.  MoviePy ≥ 2.x reads from moviepy.config;
    # older versions used the IMAGEIO_FFMPEG_EXE environment variable as a
    # fallback, set both to stay compatible across versions.
    effective = _ffmpeg_path if _ffmpeg_path else "ffmpeg"
    try:
        import moviepy.config as _mp_cfg          # MoviePy 2.x
        _mp_cfg.FFMPEG_BINARY = effective
    except (ImportError, AttributeError):
        pass
    try:
        import imageio_ffmpeg                     # MoviePy 1.x backend
        os.environ["IMAGEIO_FFMPEG_EXE"] = effective
    except ImportError:
        os.environ["IMAGEIO_FFMPEG_EXE"] = effective


def get_ffmpeg() -> str:
    """Return the ffmpeg executable to use in subprocess calls.

    Returns the user-configured path when set, otherwise 'ffmpeg' (relying
    on the system PATH).
    """
    return _ffmpeg_path if _ffmpeg_path else "ffmpeg"


def verify_ffmpeg(path: str = "") -> tuple[bool, str]:
    """Check whether *path* (or the currently configured ffmpeg) is usable.

    Returns ``(True, version_line)`` on success or ``(False, error_message)``
    on failure.  Passing an explicit *path* tests that specific executable
    without changing the stored setting.
    """
    import subprocess
    executable = (path.strip() if path else None) or get_ffmpeg()
    try:
        result = subprocess.run(
            [executable, "-version"],
            capture_output=True, text=True, timeout=5,
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        version = first_line.split()[2] if len(first_line.split()) > 2 else "installed"
        return True, version
    except FileNotFoundError:
        return False, f"'{executable}' not found, check the path or install ffmpeg"
    except Exception as exc:
        return False, str(exc)


def time_it(message: str | None = None) -> Callable:
    # Decorator that logs how long a function took to run.

    # Usage:
    #    @time_it("Hash calculated")
    #    def function(path): ...

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            label = message or f"{func.__name__} executed"
            logger.debug("%s in %.2f seconds", label, elapsed)
            return result
        return wrapper
    return decorator


def get_unique_filename(folder: str, base_name: str, extension: str) -> str:
    # Return a path that doesn't already exist, adding (1), (2), etc. as needed.
    candidate = os.path.join(folder, base_name + extension)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base_name} ({counter}){extension}")
        counter += 1
    return candidate


def get_yes_no_input(prompt: str, default_to_yes: bool = True) -> bool:
    # Ask the user a yes/no question and return True/False.

    # Empty input is treated as yes when default_to_yes=True, no otherwise.

    suffix = "(yes/y or no/n): "
    while True:
        user_input = input(f"{prompt} {suffix}").strip().lower()
        if user_input in {"yes", "y"}:
            return True
        if user_input in {"no", "n"}:
            return False
        if not user_input:
            return default_to_yes
        print("Invalid input. Please enter 'yes'/'y' or 'no'/'n'.")


import contextlib
import threading as _threading

# One lock shared across all threads. Only one thread may manipulate file-
# descriptor 2 at a time.  Without this, concurrent dup/dup2 calls from a
# ThreadPoolExecutor race against each other, each thread saving and restoring
# the wrong fd value, permanently corrupting stderr and causing hangs.
_suppress_av_lock = _threading.Lock()


@contextlib.contextmanager
def suppress_av_output():
    with _suppress_av_lock:
        try:
            import sys as _sys
            _sys.stderr.flush()
            _devnull = os.open(os.devnull, os.O_WRONLY)
            _saved   = os.dup(2)
            os.dup2(_devnull, 2)
            os.close(_devnull)
            try:
                yield
            finally:
                _sys.stderr.flush()
                os.dup2(_saved, 2)
                os.close(_saved)
        except OSError:
            yield   # suppression unavailable; run without it


def collect_files(
    folder_path: str,
    iterate_nested: bool,
    filter_by_time: bool = False,
    time_frame_hours: float = 0,
    allowed_extensions: set[str] | None = None,
) -> list[str]:
    # Walk folder_path and return a sorted list of matching file paths.

    # Pass allowed_extensions (e.g. {".mp4", ".gif"}) to filter by type,
    # or leave it as None to get everything. When filter_by_time is True,
    # only subfolders modified within the last time_frame_hours are included.

    files: list[str] = []
    current_time = time.time()

    def _allowed(name: str) -> bool:
        if allowed_extensions is None:
            return True
        return os.path.splitext(name)[1].lower() in allowed_extensions

    if iterate_nested:
        for root_dir, dirnames, filenames in os.walk(folder_path):
            if filter_by_time:
                cutoff = time_frame_hours * 3600
                # Prune dirnames in-place so os.walk doesn't descend into old ones
                dirnames[:] = [
                    d for d in dirnames
                    if current_time - os.path.getmtime(os.path.join(root_dir, d)) <= cutoff
                ]
            files.extend(
                os.path.join(root_dir, f) for f in filenames if _allowed(f)
            )
    else:
        files = [
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f)) and _allowed(f)
        ]

    return sorted(files)