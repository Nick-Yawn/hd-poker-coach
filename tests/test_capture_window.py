"""Smoke tests for window enumeration (Windows-only, stdlib).

These don't need the [capture] extra — window.py is pure ctypes.
"""

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="window capture is Windows-only"
)

from holdem_coach.capture.window import (  # noqa: E402
    WindowInfo,
    find_windows,
    list_windows,
)


def test_list_windows_returns_sane_entries():
    wins = list_windows()
    assert isinstance(wins, list)
    assert len(wins) > 0  # the test runner host always has some window
    for w in wins:
        assert isinstance(w, WindowInfo)
        assert w.title  # titled_only by default
        assert w.width > 0 and w.height > 0
        box = w.as_box()
        assert box["width"] == w.width and box["height"] == w.height


def test_find_windows_filters_by_substring():
    wins = list_windows()
    sample = wins[0].title
    needle = sample[: max(1, len(sample) // 2)]
    matches = find_windows(needle)
    titles = {m.title for m in matches}
    assert sample in titles


def test_find_windows_no_match_is_empty():
    assert find_windows("zzz_no_such_window_title_zzz_42") == []
