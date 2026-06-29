"""Screen recorder toggled from the parent menu in dev/VM.

Wraps the shared recording-setup/capture.sh and stops it with a clean SIGINT so
the .mp4 is finalized. Also finalizes on interpreter exit, so leaving Purple
(Exit to Bash, shutdown) never leaves a recording running.
"""
import atexit
import os
import signal
import subprocess
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
_CAPTURE_SH = _PROJECT_ROOT / "recording-setup" / "capture.sh"
_FRAMERATE = "30"


def _output_dir() -> Path:
    """Where to drop recordings, preferring a shared folder you can pull from
    the VM, then the project recordings/, then home."""
    shared = Path.home() / "shared"
    if shared.is_dir():
        dest = shared / "recordings"
        dest.mkdir(parents=True, exist_ok=True)
        return dest
    recordings = _PROJECT_ROOT / "recordings"
    if recordings.is_dir():
        return recordings
    return Path.home()


class Recorder:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._path: Path | None = None
        atexit.register(self.stop)

    @property
    def active(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def toggle(self) -> bool:
        """Start if idle, stop if running. Returns True if now recording."""
        if self.active:
            self.stop()
            return False
        return self.start() is not None

    def start(self) -> Path | None:
        if self.active or not _CAPTURE_SH.exists():
            return None
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self._path = _output_dir() / f"purple-recording-{stamp}.mp4"
        try:
            self._proc = subprocess.Popen(
                ["bash", str(_CAPTURE_SH), str(self._path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "PURPLE_CAPTURE_FRAMERATE": _FRAMERATE},
            )
        except OSError:
            self._proc = None
            return None
        return self._path

    def stop(self) -> Path | None:
        """SIGINT the capture so ffmpeg finalizes the file, then wait briefly."""
        if self._proc is None:
            return self._path
        if self._proc.poll() is None:
            self._proc.send_signal(signal.SIGINT)
            try:
                self._proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
        self._proc = None
        return self._path


_recorder: Recorder | None = None


def get_recorder() -> Recorder:
    global _recorder
    if _recorder is None:
        _recorder = Recorder()
    return _recorder
