"""Capture layer — PLACEHOLDER for Milestone 2 (vision adapter for HD Poker).

Do not build this until Milestone 1 produces genuinely useful coaching
(CLAUDE.md §3). When built, it observes the live table and emits the SAME
``holdem_coach.handhistory.HandHistory`` schema — that schema is the only seam.

Guardrails that bind this layer (CLAUDE.md §1):
  - Capture may run continuously, but NOTHING is surfaced for a pending decision.
  - No on-table overlay. Output lives in a separate panel only.
  - This package is HD-Poker- and resolution-specific and is expected to be
    thrown away and rewritten per UI layout. The analysis engine must never
    import from here.
"""

# Intentionally empty. See Milestone 2.
