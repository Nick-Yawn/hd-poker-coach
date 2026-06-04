"""Coaching layer — turns numbers + deltas into plain-language teaching.

CLAUDE.md §7 contract: the LLM EXPLAINS ONLY. Every quantity comes from the
analysis engine; the model never recomputes equity/EV. Mocked by default so the
Milestone 1 pipeline runs end to end without API wiring.
"""

from .coach import CoachingNote, coach_decisions

__all__ = ["CoachingNote", "coach_decisions"]
