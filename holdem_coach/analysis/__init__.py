"""Deterministic analysis engine.

Pure, testable math: equity (Monte Carlo), pot odds / required equity, simple
EV, and a decision-scorer that walks each hero decision and attaches numbers +
deltas.

CONVENTION (CLAUDE.md §9): this package must NOT import from
``holdem_coach.capture``. The HandHistory schema is the only seam. No LLM here.
"""

from .odds import required_equity, pot_odds, ev_call
from .equity import equity_vs_combos, equity_vs_range, equity_vs_random
from .ranges import RFI_RANGES, classify_hand, combos_for_class, expand_range
from .scorer import DecisionAnalysis, score_hand

__all__ = [
    "required_equity",
    "pot_odds",
    "ev_call",
    "equity_vs_combos",
    "equity_vs_range",
    "equity_vs_random",
    "RFI_RANGES",
    "classify_hand",
    "combos_for_class",
    "expand_range",
    "DecisionAnalysis",
    "score_hand",
]
