"""Capture layer — Milestone 2 vision adapter for HD Poker (Steam, Windows).

Observes the live table and (eventually) emits the SAME
``holdem_coach.handhistory.HandHistory`` schema — that schema is the only seam.
The analysis engine must never import from here (CLAUDE.md §9).

Guardrails (CLAUDE.md §1):
  - Capture may run continuously, but NOTHING is surfaced for a pending decision.
  - No on-table overlay. Output lives in a separate panel only.
  - This package is HD-Poker- and resolution-specific and is expected to be
    thrown away and rewritten per UI layout.

Current state: frame acquisition + a data-collection recorder. Recognition
(card/board/pot reading) and state tracking come next, built against real
captured frames. Heavy deps (mss, opencv, numpy) live behind the [capture]
extra and are imported lazily, so importing this package is always cheap.

Window listing works with no extra installed (stdlib ctypes); grabbing/saving
frames needs:  pip install -e ".[capture]"
"""

from .window import WindowInfo, find_window, find_windows, list_windows

__all__ = ["WindowInfo", "list_windows", "find_windows", "find_window"]
