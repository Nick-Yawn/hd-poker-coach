"""ChangeGate: skip expensive OCR on frames that haven't changed.

Compares each frame to the last one we actually *processed* (not the immediately
previous frame), so a long static stretch collapses to a single OCR. By
construction this can never skip a real change — a new card / bet / action label
is new pixels and pushes the diff above the threshold; we only ever skip frames
that are near-identical to the last processed one. The cost of a too-low
threshold is merely re-OCRing on ambient animation (harmless); a too-high
threshold risks ignoring a tiny change, so the default is conservative.

Pure-ish: cv2/numpy imported lazily; the math is testable with synthetic frames.
"""

from __future__ import annotations


class ChangeGate:
    def __init__(self, *, threshold: float = 2.5, size: tuple[int, int] = (96, 64)):
        # threshold is mean absolute 0-255 intensity diff over the downscaled,
        # blurred grayscale frame. ~1-2 is ambient (water/avatars); real table
        # changes run higher.
        self.threshold = threshold
        self.size = size
        self._ref = None

    def _digest(self, frame):
        import cv2

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, self.size, interpolation=cv2.INTER_AREA)
        return cv2.GaussianBlur(small, (3, 3), 0).astype("float32")

    def changed(self, frame) -> bool:
        """True if `frame` differs from the last processed frame (and updates
        the reference). Always True on the first call."""
        import numpy as np

        cur = self._digest(frame)
        if self._ref is None:
            self._ref = cur
            return True
        diff = float(np.abs(cur - self._ref).mean())
        if diff >= self.threshold:
            self._ref = cur
            return True
        return False

    def reset(self) -> None:
        self._ref = None
