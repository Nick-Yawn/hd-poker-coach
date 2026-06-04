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


def test_classify_suit_on_real_feature_values():
    # Real (solidity, extent) measured across two table themes.
    assert _classify_suit("black", 0.762, 0.507) == "c"  # Jc
    assert _classify_suit("black", 0.807, 0.665) == "c"  # 6c (the one that misread)
    assert _classify_suit("black", 0.911, 0.573) == "s"  # 4s
    assert _classify_suit("black", 0.907, 0.587) == "s"  # 9s
    assert _classify_suit("red", 0.882, 0.475) == "d"    # Kd
    assert _classify_suit("red", 0.947, 0.644) == "h"    # 8h


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


def test_hero_card_region_is_constant_offset_above_seat():
    from holdem_coach.capture.cards import hero_card_region

    # Cards sit a fixed amount ABOVE the nameplate, same at any seat.
    for cx, cy in [(0.50, 0.81), (0.30, 0.26), (0.72, 0.50)]:
        x, y, w, h = hero_card_region(cx, cy)
        center_x = x + w / 2
        center_y = y + h / 2
        assert abs(center_x - cx) < 1e-6          # horizontally centered on seat
        assert abs(center_y - (cy - 0.09)) < 1e-6  # ~0.09 above the seat


HERO_FIXTURE = Path(__file__).parent / "fixtures" / "hero_Kd5s.png"


@pytest.mark.skipif(not HERO_FIXTURE.exists(), reason="hero fixture missing")
def test_read_hero_hole_cards_fixture():
    from holdem_coach.capture.cards import read_card_row

    row = cv2.imread(str(HERO_FIXTURE))
    assert read_card_row(row) == ["Kd", "5s"]
