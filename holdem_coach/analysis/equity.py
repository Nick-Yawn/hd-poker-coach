"""Monte Carlo equity using the ``treys`` 7-card evaluator (CLAUDE.md §4, §6).

Equity = (wins + ties/2) / iterations, evaluating the hero's hole cards against
an opponent drawn from a supplied combo list (or a random hand) over the
remaining board run-outs.

All public functions accept an optional ``seed`` so tests are deterministic.
"""

from __future__ import annotations

import random

from treys import Card, Evaluator

from .ranges import expand_range

_EVAL = Evaluator()

# Full 52-card deck in treys-int form, keyed by notation.
_DECK: dict[str, int] = {
    r + s: Card.new(r + s) for r in "23456789TJQKA" for s in "shdc"
}


def _ints(cards) -> list[int]:
    return [_DECK[c] for c in cards]


def equity_vs_combos(
    hero: list[str],
    board: list[str],
    opp_combos: list[tuple[str, str]],
    *,
    dead: list[str] | None = None,
    iterations: int = 10_000,
    seed: int | None = None,
) -> float:
    """Hero equity vs a uniform draw from ``opp_combos`` over remaining run-outs.

    ``board`` may be 0, 3, 4, or 5 cards; the run-out is completed to 5.
    Combos that collide with hero/board/dead cards are filtered out. Returns a
    float in [0, 1]; raises ValueError if no legal opponent combo remains.
    """
    rng = random.Random(seed)
    hero_i = _ints(hero)
    board_i = _ints(board)
    dead_i = _ints(dead or [])
    blocked = set(hero_i) | set(board_i) | set(dead_i)

    legal: list[tuple[int, int]] = []
    for c1, c2 in opp_combos:
        i1, i2 = _DECK[c1], _DECK[c2]
        if i1 in blocked or i2 in blocked or i1 == i2:
            continue
        legal.append((i1, i2))
    if not legal:
        raise ValueError("no legal opponent combos after removing blockers")

    need = 5 - len(board_i)
    full = list(_DECK.values())
    wins = ties = 0

    for _ in range(iterations):
        o1, o2 = rng.choice(legal)
        used = blocked | {o1, o2}
        if need:
            remaining = [c for c in full if c not in used]
            runout = rng.sample(remaining, need)
        else:
            runout = []
        final_board = board_i + runout
        hero_score = _EVAL.evaluate(final_board, hero_i)
        opp_score = _EVAL.evaluate(final_board, [o1, o2])
        if hero_score < opp_score:        # lower is better in treys
            wins += 1
        elif hero_score == opp_score:
            ties += 1

    return (wins + ties / 2) / iterations


def equity_vs_random(
    hero: list[str],
    board: list[str] | None = None,
    *,
    dead: list[str] | None = None,
    iterations: int = 10_000,
    seed: int | None = None,
) -> float:
    """Hero equity vs a uniformly random opponent hand."""
    board = board or []
    blocked = set(hero) | set(board) | set(dead or [])
    remaining = [c for c in _DECK if c not in blocked]
    combos = [
        (remaining[i], remaining[j])
        for i in range(len(remaining))
        for j in range(i + 1, len(remaining))
    ]
    return equity_vs_combos(
        hero, board, combos, dead=dead, iterations=iterations, seed=seed
    )


def equity_vs_range(
    hero: list[str],
    board: list[str] | None,
    hand_classes,
    *,
    dead: list[str] | None = None,
    iterations: int = 10_000,
    seed: int | None = None,
) -> float:
    """Hero equity vs an opponent range given as hand classes (e.g. {'AA','AKs'})."""
    return equity_vs_combos(
        hero,
        board or [],
        expand_range(hand_classes),
        dead=dead,
        iterations=iterations,
        seed=seed,
    )
