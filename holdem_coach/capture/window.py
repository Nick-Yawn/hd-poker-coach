"""Windows window enumeration + geometry (stdlib ctypes only).

Used to locate the HD Poker game window and get its on-screen rectangle so the
frame grabber knows what to capture. No third-party deps here, so listing
windows works even before the [capture] extra is installed.

Windows-only. On other platforms these functions raise RuntimeError.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32

    # Set argtypes/restypes so 64-bit HWND handles are not truncated to int.
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetClientRect.restype = wintypes.BOOL
    _user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    _user32.ClientToScreen.restype = wintypes.BOOL

    _EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_EnumProc, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    left: int
    top: int
    width: int
    height: int

    def as_box(self) -> dict:
        """mss-style bounding box for the full window rectangle."""
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


def _require_windows() -> None:
    if not _IS_WINDOWS:
        raise RuntimeError("window capture is only supported on Windows")


def ensure_dpi_aware() -> None:
    """Make this process per-monitor DPI aware so window rects match real pixels.

    Without this, on a scaled display the rectangles returned here and the pixels
    mss captures disagree, and every region is misaligned. Best-effort; ignored
    where unavailable.
    """
    if not _IS_WINDOWS:
        return
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _window_title(hwnd) -> str:
    length = _user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def list_windows(*, visible_only: bool = True, titled_only: bool = True) -> list[WindowInfo]:
    """All top-level windows, most-recently as enumerated by the OS."""
    _require_windows()
    results: list[WindowInfo] = []

    def _callback(hwnd, _lparam):
        if visible_only and not _user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd)
        if titled_only and not title:
            return True
        rect = wintypes.RECT()
        if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return True
        results.append(WindowInfo(int(hwnd), title, rect.left, rect.top, w, h))
        return True

    _user32.EnumWindows(_EnumProc(_callback), 0)
    return results


def find_windows(title_substr: str, **kwargs) -> list[WindowInfo]:
    """Windows whose title contains ``title_substr`` (case-insensitive)."""
    needle = title_substr.lower()
    return [w for w in list_windows(**kwargs) if needle in w.title.lower()]


def find_window(title_substr: str, **kwargs) -> WindowInfo:
    """Exactly one matching window, or raise a helpful error."""
    matches = find_windows(title_substr, **kwargs)
    if not matches:
        raise RuntimeError(
            f"no visible window matching {title_substr!r}. "
            "Run `holdem-coach windows` to list candidates."
        )
    if len(matches) > 1:
        titles = ", ".join(repr(m.title) for m in matches[:6])
        raise RuntimeError(
            f"{len(matches)} windows match {title_substr!r}: {titles}. "
            "Use a more specific substring."
        )
    return matches[0]


def client_box(window: WindowInfo) -> dict:
    """mss box for the window's *client* area (excludes title bar / borders)."""
    _require_windows()
    hwnd = window.hwnd
    rect = wintypes.RECT()
    _user32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    _user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return {
        "left": origin.x,
        "top": origin.y,
        "width": rect.right - rect.left,
        "height": rect.bottom - rect.top,
    }
