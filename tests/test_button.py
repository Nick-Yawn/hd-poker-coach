import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from holdem_coach.capture.button import find_button_name
from holdem_coach.capture.tablestate import SeatState


def _teal_bgr():
    return cv2.cvtColor(np.uint8([[[95, 200, 200]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()


def _paint_badge(frame, cx, cy):
    h, w = frame.shape[:2]
    x0, x1 = int((cx + 0.045) * w), int((cx + 0.07) * w)
    y0, y1 = int((cy + 0.015) * h), int((cy + 0.030) * h)
    frame[y0:y1, x0:x1] = _teal_bgr()


def test_find_button_name_detects_the_badge_seat():
    frame = np.full((500, 800, 3), 30, np.uint8)  # dark background
    a = SeatState(name="alice", cx=0.30, cy=0.50)
    b = SeatState(name="bob", cx=0.60, cy=0.50)
    _paint_badge(frame, a.cx, a.cy)  # only alice has the badge
    assert find_button_name(frame, [a, b]) == "alice"


def test_find_button_name_none_when_no_badge():
    frame = np.full((500, 800, 3), 30, np.uint8)
    seats = [SeatState(name="alice", cx=0.30, cy=0.50),
             SeatState(name="bob", cx=0.60, cy=0.50)]
    assert find_button_name(frame, seats) is None
