"""Dealer-button detection via the nameplate badge.

HD Poker marks the button player with a small teal disc + white "D" at the
INSIDE bottom-right corner of their nameplate. We check that tight region on each
seat's plate for the badge's teal (hue ~95) — kept narrow so the action drawer
below the plate and the teal bet pills toward the centre stay out. The seat whose
plate has the badge is the button; positions then follow by clockwise rotation
(no blinds needed).

Validated on two real frames: clean separation (button plate ~0.015 teal-fraction
vs 0.000 for every other plate). Heavy deps (cv2) imported lazily.
"""

from __future__ import annotations

# Badge region relative to the name-token centre (frame fractions), and the
# teal-fraction threshold (button plate ~0.015; others ~0).
_BADGE_DX = (0.035, 0.082)
_BADGE_DY = (0.010, 0.036)
_BADGE_MIN = 0.006


def _badge_teal_fraction(frame, cx: float, cy: float) -> float:
    import cv2

    h, w = frame.shape[:2]
    x0 = int((cx + _BADGE_DX[0]) * w)
    x1 = int((cx + _BADGE_DX[1]) * w)
    y0 = int((cy + _BADGE_DY[0]) * h)
    y1 = int((cy + _BADGE_DY[1]) * h)
    reg = frame[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]
    if reg.size == 0:
        return 0.0
    hsv = cv2.cvtColor(reg, cv2.COLOR_BGR2HSV)
    teal = (
        (hsv[..., 0] >= 90) & (hsv[..., 0] <= 102)
        & (hsv[..., 1] > 90) & (hsv[..., 2] > 90)
    )
    return float(teal.mean())


def find_button_name(frame, seats) -> str | None:
    """Return the name of the seat marked with the dealer button, or None."""
    best_name = None
    best_frac = 0.0
    for s in seats:
        if not s.name:
            continue
        frac = _badge_teal_fraction(frame, s.cx, s.cy)
        if frac > best_frac:
            best_name, best_frac = s.name, frac
    return best_name if best_frac >= _BADGE_MIN else None
