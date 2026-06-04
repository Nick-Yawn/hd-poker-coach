"""Pot odds, required equity, and simple single-decision EV (CLAUDE.md §6).

All pure functions. No randomness, no I/O.
"""

from __future__ import annotations


def required_equity(call_amount: float, pot: float) -> float:
    """Equity needed to break even on a call.

    Per CLAUDE.md §6: to call ``C`` into a pot of ``P`` (where ``P`` already
    includes the bet faced), required equity = ``C / (P + C)``.

    ``pot`` here is the pot *before* the hero puts the call in but *including*
    the bet the hero is facing.
    """
    denom = pot + call_amount
    if denom <= 0:
        return 0.0
    return call_amount / denom


# Pot odds and required-equity-to-call are the same number expressed two ways;
# expose both names so call sites read naturally.
pot_odds = required_equity


def ev_call(equity: float, pot_won: float, amount_risked: float) -> float:
    """Simple single-decision EV of calling.

    EV(call) ≈ equity * pot_won − (1 − equity) * amount_risked   (CLAUDE.md §6)

    ``pot_won`` is what the hero collects when they win (the pot *not* counting
    the hero's own call); ``amount_risked`` is the chips the hero puts in to
    call. This is the tractable single-street approximation — multi-street EV
    needs a solver and is deliberately out of scope for Milestone 1.
    """
    return equity * pot_won - (1.0 - equity) * amount_risked
