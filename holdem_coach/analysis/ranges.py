"""Static position-based preflop opening (RFI) ranges for 6-max cash.

Milestone 1 baseline only (CLAUDE.md §4): hand-authored opening charts, NOT a
solver. They exist so the scorer can flag obviously out-of-range opens and so we
can estimate a raiser's range for equity. Solver integration is a later
enhancement.

A "hand class" is the canonical shorthand: pairs ("AA"), suited ("AKs"), or
offsuit ("AKo"). Helpers expand a class into its concrete 2-card combos.
"""

from __future__ import annotations

from itertools import combinations

RANKS = "23456789TJQKA"
SUITS = "cdhs"


def _ridx(r: str) -> int:
    return RANKS.index(r)


# --------------------------------------------------------------------------- #
# Hand-class <-> combos
# --------------------------------------------------------------------------- #
def classify_hand(card_a: str, card_b: str) -> str:
    """Return the canonical class for two cards, e.g. ('Ah','Kd') -> 'AKo'."""
    ra, sa = card_a[0], card_a[1]
    rb, sb = card_b[0], card_b[1]
    # High rank first.
    if _ridx(ra) < _ridx(rb):
        ra, rb, sa, sb = rb, ra, sb, sa
    if ra == rb:
        return ra + rb
    return f"{ra}{rb}{'s' if sa == sb else 'o'}"


def combos_for_class(cls: str) -> list[tuple[str, str]]:
    """Expand a hand class into its concrete card combos.

    Pairs -> 6 combos, suited -> 4 combos, offsuit -> 12 combos.
    """
    if len(cls) == 2:  # pair, e.g. "AA"
        r = cls[0]
        return [(r + s1, r + s2) for s1, s2 in combinations(SUITS, 2)]
    r1, r2, kind = cls[0], cls[1], cls[2]
    if kind == "s":
        return [(r1 + s, r2 + s) for s in SUITS]
    if kind == "o":
        return [(r1 + s1, r2 + s2) for s1 in SUITS for s2 in SUITS if s1 != s2]
    raise ValueError(f"unrecognized hand class: {cls!r}")


def expand_range(classes) -> list[tuple[str, str]]:
    """Flatten an iterable of hand classes into all concrete combos."""
    out: list[tuple[str, str]] = []
    for cls in classes:
        out.extend(combos_for_class(cls))
    return out


# --------------------------------------------------------------------------- #
# Range builders (by rank run)
# --------------------------------------------------------------------------- #
def _pairs(min_rank: str) -> set[str]:
    return {r + r for r in RANKS if _ridx(r) >= _ridx(min_rank)}


def _suited(high: str, low_min: str) -> set[str]:
    """e.g. _suited('A','2') -> {A2s..AKs}."""
    return {
        f"{high}{x}s" for x in RANKS if _ridx(low_min) <= _ridx(x) < _ridx(high)
    }


def _offsuit(high: str, low_min: str) -> set[str]:
    return {
        f"{high}{x}o" for x in RANKS if _ridx(low_min) <= _ridx(x) < _ridx(high)
    }


# 6-max RFI charts. Progressively wider by position. These are reasonable study
# defaults, not solver output; tune freely.
_UTG: set[str] = (
    _pairs("2")
    | _suited("A", "2")
    | _suited("K", "9")
    | _suited("Q", "9")
    | _suited("J", "9")
    | _suited("T", "8")
    | {"98s", "87s", "76s", "65s"}
    | _offsuit("A", "J")
    | {"KQo"}
)

_MP: set[str] = (
    _UTG
    | _suited("K", "7")
    | _suited("Q", "8")
    | {"T7s", "97s", "86s", "75s", "54s"}
    | _offsuit("A", "T")
    | {"KJo", "KTo", "QJo"}
)

_CO: set[str] = (
    _MP
    | _suited("K", "5")
    | _suited("Q", "7")
    | _suited("J", "8")
    | {"T6s", "96s", "85s", "64s", "53s", "43s"}
    | _offsuit("A", "8")
    | _offsuit("K", "T")
    | {"QTo", "JTo", "T9o"}
)

_BTN: set[str] = (
    _CO
    | _suited("K", "2")
    | _suited("Q", "4")
    | _suited("J", "6")
    | _suited("T", "6")
    | {"95s", "84s", "74s", "63s", "52s", "42s", "32s"}
    | _offsuit("A", "2")
    | _offsuit("K", "7")
    | _offsuit("Q", "9")
    | {"J9o", "J8o", "98o", "T8o"}
)

# SB has no "fold to a raise" option in our RFI sense; use a CO-like open/raise
# chart as the SB raise-first-in baseline.
_SB: set[str] = _CO | _suited("Q", "5") | _offsuit("A", "5") | {"K9o", "QTo"}

# BB never opens (it can only defend), but we expose a wide reference defense set
# so estimate-range logic has something for a BB caller.
_BB: set[str] = _BTN | _offsuit("Q", "6") | _offsuit("J", "7") | _offsuit("T", "7")

RFI_RANGES: dict[str, frozenset[str]] = {
    "UTG": frozenset(_UTG),
    "MP": frozenset(_MP),
    "CO": frozenset(_CO),
    "BTN": frozenset(_BTN),
    "SB": frozenset(_SB),
    "BB": frozenset(_BB),
}


def opening_range(position: str) -> frozenset[str]:
    """RFI hand classes for a position; empty frozenset if unknown."""
    return RFI_RANGES.get(position, frozenset())
