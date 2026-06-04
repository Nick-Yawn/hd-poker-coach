import math

from conftest import SAMPLE_DIR

from holdem_coach.analysis.scorer import score_hand
from holdem_coach.handhistory import HandHistory


def _load(name):
    return HandHistory.load(SAMPLE_DIR / name)


def test_hand1_flags_loose_preflop_open():
    hh = _load("hand1_preflop_mistake.json")
    decisions = score_hand(hh, iterations=2000, seed=1)
    preflop = decisions[0]
    assert preflop.street == "preflop"
    assert preflop.hero_class == "K9o"
    assert preflop.leak is True
    assert preflop.tag == "LEAK"
    assert preflop.concept == "preflop range"


def test_hand1_hero_has_three_decisions():
    hh = _load("hand1_preflop_mistake.json")
    decisions = score_hand(hh, iterations=1000, seed=1)
    # preflop raise, flop bet, turn bet
    assert [d.street for d in decisions] == ["preflop", "flop", "turn"]


def test_pot_reconstruction_matches_amounts():
    # Hand 1: at the hero's flop bet, the pot before acting should be 13
    # (preflop: SB1 + BB6 + UTG6 = 13).
    hh = _load("hand1_preflop_mistake.json")
    decisions = score_hand(hh, iterations=500, seed=1)
    flop = next(d for d in decisions if d.street == "flop")
    assert flop.pot_before == 13


def test_hand2_flop_call_is_pot_odds_decision():
    hh = _load("hand2_pot_odds.json")
    decisions = score_hand(hh, iterations=3000, seed=1)
    # The hero acts twice on the flop (check, then call vs the bet); the
    # pot-odds decision is the call.
    flop = next(
        d for d in decisions if d.street == "flop" and d.hero_action == "call"
    )
    assert flop.facing_bet is True
    # Call 6 into pot 19 -> need 6/25 = 0.24.
    assert math.isclose(flop.required_equity, 0.24, rel_tol=1e-9)
    assert flop.concept == "pot odds"
    # Nut flush draw + overcard has more than the required price.
    assert flop.equity > flop.required_equity
    assert flop.ev_call > 0
    assert flop.leak is False


def test_hand3_clean_line_has_no_leaks():
    hh = _load("hand3_clean_line.json")
    decisions = score_hand(hh, iterations=2000, seed=1)
    assert all(d.leak is False for d in decisions)
    preflop = decisions[0]
    assert preflop.hero_class == "AKo"
    assert preflop.tag == "OK"


def test_equities_are_probabilities():
    for name in (
        "hand1_preflop_mistake.json",
        "hand2_pot_odds.json",
        "hand3_clean_line.json",
    ):
        for d in score_hand(_load(name), iterations=500, seed=1):
            assert 0.0 <= d.equity <= 1.0
