"""Card-reader tests.

The image test uses a committed, privacy-safe fixture (community cards only).
Pure-logic tests (rank normalization, suit classification) need no image.
"""

from pathlib import Path

import pytest

from holdem_coach.capture.cards import _classify_suit, _norm_rank

cv2 = pytest.importorskip("cv2")  # needs the [capture] extra

FIXTURE = Path(__file__).parent / "fixtures" / "board_Jc8d4s2s8h.png"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("J*", "J"), ("8", "8"), ("4", "4"), ("A", "A"), ("Q", "Q"),
        ("10", "T"), ("1O", "T"), ("K.", "K"), ("", None), ("xx", None),
    ],
)
def test_norm_rank(text, expected):
    assert _norm_rank(text) == expected


def test_classify_suit_centroids():
    # Feature points near each suit's reference centroid classify correctly.
    assert _classify_suit("black", 0.76, 0.51) == "c"
    assert _classify_suit("black", 0.92, 0.61) == "s"
    assert _classify_suit("red", 0.90, 0.46) == "d"
    assert _classify_suit("red", 0.95, 0.64) == "h"


def test_classify_suit_respects_colour():
    # A black-coloured card never returns a red suit, and vice versa.
    assert _classify_suit("black", 0.95, 0.64) in ("c", "s")
    assert _classify_suit("red", 0.76, 0.51) in ("d", "h")


@pytest.mark.skipif(not FIXTURE.exists(), reason="board fixture missing")
def test_read_board_fixture():
    from holdem_coach.capture.cards import read_card_row

    row = cv2.imread(str(FIXTURE))
    cards = read_card_row(row)
    assert cards == ["Jc", "8d", "4s", "2s", "8h"]
