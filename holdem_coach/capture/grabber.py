"""Frame acquisition: grab pixels from a window (or monitor) as BGR arrays.

Heavy deps (mss, numpy) are imported lazily so importing the package — and the
rest of the app — never requires the [capture] extra. Install it with:
    pip install -e ".[capture]"

The grabber re-resolves the target window's rectangle on every grab, so it keeps
working if the window is moved or resized between frames.
"""

from __future__ import annotations

from .window import WindowInfo, client_box, ensure_dpi_aware, find_window


def _require_capture_deps():
    try:
        import mss  # noqa: F401
        import numpy as np  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "frame capture needs the [capture] extra. Install it with:\n"
            '  pip install -e ".[capture]"'
        ) from exc
    return mss, np


class WindowGrabber:
    """Grabs frames from the first window matching ``title_substr``.

    ``client=True`` captures just the client area (no title bar / borders),
    which is usually what you want for a game's render surface.
    """

    def __init__(self, title_substr: str, *, client: bool = True) -> None:
        ensure_dpi_aware()
        self._mss, self._np = _require_capture_deps()
        self.title_substr = title_substr
        self.client = client
        self._sct = self._mss.mss()

    def resolve(self) -> WindowInfo:
        return find_window(self.title_substr)

    def _box(self) -> dict:
        win = self.resolve()
        return client_box(win) if self.client else win.as_box()

    def grab(self):
        """Return the current frame as a BGR ``numpy`` array (H, W, 3)."""
        box = self._box()
        if box["width"] <= 0 or box["height"] <= 0:
            raise RuntimeError(f"target window has a non-positive size: {box}")
        raw = self._sct.grab(box)
        # mss yields BGRA; drop alpha to BGR for OpenCV.
        frame = self._np.asarray(raw, dtype=self._np.uint8)[:, :, :3]
        return frame

    def close(self) -> None:
        try:
            self._sct.close()
        except Exception:
            pass

    def __enter__(self) -> "WindowGrabber":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class MonitorGrabber:
    """Grabs a whole monitor (1-indexed; 0 = the full virtual screen).

    Handy for testing the capture path without a specific target window.
    """

    def __init__(self, monitor: int = 1) -> None:
        ensure_dpi_aware()
        self._mss, self._np = _require_capture_deps()
        self.monitor = monitor
        self._sct = self._mss.mss()

    def grab(self):
        mons = self._sct.monitors  # [0]=all, [1..]=individual
        if not (0 <= self.monitor < len(mons)):
            raise RuntimeError(
                f"monitor {self.monitor} out of range (have {len(mons) - 1} monitors)"
            )
        raw = self._sct.grab(mons[self.monitor])
        return self._np.asarray(raw, dtype=self._np.uint8)[:, :, :3]

    def close(self) -> None:
        try:
            self._sct.close()
        except Exception:
            pass

    def __enter__(self) -> "MonitorGrabber":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
