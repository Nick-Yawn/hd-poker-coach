import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from holdem_coach.capture.changegate import ChangeGate


def _frame(fill, *, patch=None):
    img = np.full((200, 300, 3), fill, dtype=np.uint8)
    if patch is not None:
        (x, y, w, h), val = patch
        img[y:y + h, x:x + w] = val
    return img


def test_first_frame_always_changed():
    gate = ChangeGate()
    assert gate.changed(_frame(100)) is True


def test_identical_frame_is_skipped():
    gate = ChangeGate()
    f = _frame(100)
    assert gate.changed(f) is True
    assert gate.changed(f.copy()) is False


def test_localized_change_is_detected():
    gate = ChangeGate(threshold=2.5)
    assert gate.changed(_frame(100)) is True
    # A bright patch (like a card/bet appearing) must register as changed.
    changed = _frame(100, patch=((120, 80, 60, 40), 255))
    assert gate.changed(changed) is True


def test_tiny_noise_below_threshold_is_skipped():
    gate = ChangeGate(threshold=2.5)
    base = _frame(100)
    assert gate.changed(base) is True
    # Uniform +1 intensity everywhere is well under the threshold.
    assert gate.changed(_frame(101)) is False


def test_reference_is_last_processed_frame():
    # A slow drift that never individually exceeds the threshold vs the last
    # PROCESSED frame keeps getting skipped (reference doesn't advance).
    gate = ChangeGate(threshold=5.0)
    assert gate.changed(_frame(100)) is True
    for fill in (101, 102, 103):
        assert gate.changed(_frame(fill)) is False
    # Now a jump beyond threshold vs the original reference (100) registers.
    assert gate.changed(_frame(120)) is True
