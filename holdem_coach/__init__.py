"""Hold'em Study Coach — post-hand analysis + coaching for Texas Hold'em.

Package layout:
  holdem_coach.handhistory  the durable HandHistory schema (the only seam)
  holdem_coach.analysis      deterministic math: equity, pot odds, EV, scoring
  holdem_coach.coaching      LLM layer: turns numbers + deltas into English
  holdem_coach.capture       placeholder for the Milestone 2 vision adapter

Guardrail: this is a *post-hand* tool. Nothing here surfaces output for a
pending decision. See CLAUDE.md §1.
"""

__version__ = "0.1.0"
