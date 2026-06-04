import json

import pytest
from conftest import SAMPLE_DIR

from holdem_coach.handhistory import HandHistory, HandHistoryError, is_valid_card

ALL_SAMPLES = sorted(SAMPLE_DIR.glob("*.json"))


def test_samples_exist():
    assert len(ALL_SAMPLES) == 3


@pytest.mark.parametrize("path", ALL_SAMPLES, ids=lambda p: p.stem)
def test_sample_loads_and_validates(path):
    hh = HandHistory.load(path)  # load() validates internally
    assert hh.hero_position is not None
    assert len(hh.hero_hole_cards) == 2


@pytest.mark.parametrize("path", ALL_SAMPLES, ids=lambda p: p.stem)
def test_json_round_trip_is_stable(path):
    hh = HandHistory.load(path)
    again = HandHistory.from_json(hh.to_json())
    assert again.to_dict() == hh.to_dict()


def test_card_validator():
    assert is_valid_card("Ah")
    assert is_valid_card("Tc")
    assert not is_valid_card("ah")   # lowercase rank
    assert not is_valid_card("AH")   # uppercase suit
    assert not is_valid_card("10h")  # wrong ten notation
    assert not is_valid_card("Z2")


def _base_dict():
    return {
        "hand_id": "t",
        "table": {"max_seats": 6, "small_blind": 1, "big_blind": 2},
        "hero_seat": 1,
        "button_seat": 1,
        "players": [
            {"seat": 1, "position": "BTN", "starting_stack": 200},
            {"seat": 2, "position": "BB", "starting_stack": 200},
        ],
        "hero_hole_cards": ["Ah", "Kd"],
        "board": {"flop": [], "turn": None, "river": None},
        "actions": [],
        "result": {"winning_seats": [1], "pot": 3, "hero_net": 1},
    }


def test_invalid_card_rejected():
    d = _base_dict()
    d["hero_hole_cards"] = ["Ah", "Xx"]
    with pytest.raises(HandHistoryError):
        HandHistory.from_dict(d)


def test_duplicate_card_rejected():
    d = _base_dict()
    d["hero_hole_cards"] = ["Ah", "Ah"]
    with pytest.raises(HandHistoryError):
        HandHistory.from_dict(d)


def test_duplicate_card_across_hole_and_board_rejected():
    d = _base_dict()
    d["board"] = {"flop": ["Ah", "2c", "3d"], "turn": None, "river": None}
    with pytest.raises(HandHistoryError):
        HandHistory.from_dict(d)


def test_hero_seat_must_be_a_player():
    d = _base_dict()
    d["hero_seat"] = 9
    with pytest.raises(HandHistoryError):
        HandHistory.from_dict(d)


def test_action_unknown_seat_rejected():
    d = _base_dict()
    d["actions"] = [{"street": "preflop", "seat": 99, "action": "fold"}]
    with pytest.raises(HandHistoryError):
        HandHistory.from_dict(d)
