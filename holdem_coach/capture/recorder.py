"""Save frames to disk for offline development of the recognizer.

This is a *data-collection* tool, not part of the live pipeline: it grabs frames
and writes PNGs so we can build card templates / OCR digit templates and define
regions of interest against real HD Poker pixels.

Guardrail (CLAUDE.md §1): recording is passive observation only. It never shows
analysis or any hint while a hand is live — it just writes images.
"""

from __future__ import annotations

import time
from pathlib import Path


def _cv2():
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - optional extra
        raise RuntimeError(
            'saving frames needs the [capture] extra: pip install -e ".[capture]"'
        ) from exc
    return cv2


def save_frame(frame, path: str | Path) -> Path:
    """Write a single BGR frame to ``path`` (PNG)."""
    cv2 = _cv2()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), frame):
        raise RuntimeError(f"failed to write frame to {path}")
    return path


def record(
    grabber,
    out_dir: str | Path,
    *,
    interval: float = 1.0,
    count: int | None = None,
    prefix: str = "frame",
    on_save=None,
) -> int:
    """Grab frames every ``interval`` seconds into ``out_dir``.

    Runs ``count`` frames, or until interrupted (Ctrl+C) when ``count`` is None.
    Returns the number of frames written. ``on_save(index, path)`` is called
    after each save (e.g. for progress printing).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved = 0
    try:
        while count is None or saved < count:
            tick = time.perf_counter()
            frame = grabber.grab()
            path = out / f"{prefix}_{saved:05d}.png"
            save_frame(frame, path)
            if on_save is not None:
                on_save(saved, path)
            saved += 1
            # Sleep the remainder of the interval (account for grab/encode time).
            elapsed = time.perf_counter() - tick
            remaining = interval - elapsed
            if remaining > 0 and (count is None or saved < count):
                time.sleep(remaining)
    except KeyboardInterrupt:
        pass
    return saved
