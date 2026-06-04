import math

from holdem_coach.analysis.odds import ev_call, pot_odds, required_equity


def test_required_equity_basic():
    # Call 6 into a pot of 12 (already including the bet faced): 6/(12+6)=1/3.
    assert math.isclose(required_equity(6, 12), 1 / 3, rel_tol=1e-9)


def test_required_equity_half_pot_bet_line():
    # Call 6 into 19 -> 6/25 = 0.24
    assert math.isclose(required_equity(6, 19), 0.24, rel_tol=1e-9)


def test_pot_odds_is_required_equity():
    assert pot_odds(4, 9) == required_equity(4, 9)


def test_required_equity_zero_call():
    assert required_equity(0, 10) == 0.0


def test_required_equity_degenerate_pot():
    assert required_equity(0, 0) == 0.0


def test_ev_call_break_even_at_required_equity():
    # At exactly the required equity, EV of calling should be ~0.
    pot, call = 12.0, 6.0
    eq = required_equity(call, pot)
    assert math.isclose(ev_call(eq, pot, call), 0.0, abs_tol=1e-9)


def test_ev_call_positive_when_equity_beats_price():
    pot, call = 12.0, 6.0
    assert ev_call(0.5, pot, call) > 0


def test_ev_call_negative_when_equity_short():
    pot, call = 12.0, 6.0
    assert ev_call(0.2, pot, call) < 0
