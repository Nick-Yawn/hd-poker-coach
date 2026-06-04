"""Equity tests against known values (CLAUDE.md §8 task 4).

Monte Carlo with a fixed seed; tolerances are wide enough to be robust but tight
enough to catch real regressions.
"""

from holdem_coach.analysis.equity import (
    equity_vs_combos,
    equity_vs_random,
    equity_vs_range,
)

ITERS = 20_000
SEED = 7


def test_aa_vs_kk_preflop_about_81pct():
    # The canonical sanity check: AA is ~81-82% over KK preflop.
    eq = equity_vs_combos(
        ["Ah", "Ad"], [], [("Kc", "Ks")], iterations=ITERS, seed=SEED
    )
    assert 0.78 <= eq <= 0.85


def test_aa_vs_random_about_85pct():
    eq = equity_vs_random(["Ah", "Ad"], iterations=ITERS, seed=SEED)
    assert 0.83 <= eq <= 0.88


def test_72o_vs_random_is_worst_hand():
    eq = equity_vs_random(["7h", "2c"], iterations=ITERS, seed=SEED)
    # 72o is the worst starting hand; clearly below 50% vs random.
    assert 0.30 <= eq <= 0.40


def test_equity_is_symmetric_complement():
    hero = equity_vs_combos(
        ["Ah", "Ad"], [], [("Kc", "Ks")], iterations=ITERS, seed=SEED
    )
    villain = equity_vs_combos(
        ["Kc", "Ks"], [], [("Ah", "Ad")], iterations=ITERS, seed=SEED
    )
    # Heads-up equities should sum to ~1 (ties split, so allow slack).
    assert abs((hero + villain) - 1.0) < 0.03


def test_made_flush_on_river_is_certain():
    # Hero has the nut flush on a complete board; villain (7s8c) can't beat it
    # (the 2-2 board pair can't make villain a full house without a deuce).
    eq = equity_vs_combos(
        ["Ah", "5h"],
        ["Kh", "9h", "2c", "2d", "Qh"],
        [("7s", "8c")],
        iterations=2_000,
        seed=SEED,
    )
    assert eq == 1.0


def test_equity_vs_range_runs_and_bounded():
    eq = equity_vs_range(
        ["Ah", "Kd"], ["Ad", "7c", "2h"], {"QQ", "JJ", "AKs"},
        iterations=5_000, seed=SEED,
    )
    assert 0.0 <= eq <= 1.0
