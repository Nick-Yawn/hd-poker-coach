from holdem_coach.analysis.ranges import (
    classify_hand,
    combos_for_class,
    expand_range,
    opening_range,
)


def test_classify_pair():
    assert classify_hand("Ah", "Ad") == "AA"


def test_classify_suited_orders_high_first():
    assert classify_hand("Kd", "Ad") == "AKs"
    assert classify_hand("Ad", "Kd") == "AKs"


def test_classify_offsuit():
    assert classify_hand("Ah", "Kd") == "AKo"
    assert classify_hand("9c", "Kh") == "K9o"


def test_combo_counts():
    assert len(combos_for_class("AA")) == 6
    assert len(combos_for_class("AKs")) == 4
    assert len(combos_for_class("AKo")) == 12


def test_combos_are_unique_and_legal():
    for cls in ("AA", "AKs", "AKo", "72o"):
        combos = combos_for_class(cls)
        flat = {frozenset(c) for c in combos}
        assert len(flat) == len(combos)  # no duplicate combos
        for a, b in combos:
            assert a != b  # never the same physical card twice


def test_expand_range_sums_combos():
    combos = expand_range({"AA", "AKs"})
    assert len(combos) == 6 + 4


def test_utg_is_tight_btn_is_wide():
    utg = opening_range("UTG")
    btn = opening_range("BTN")
    # The loose-open leak hand in sample 1:
    assert "K9o" not in utg
    assert "AKs" in utg and "AKs" in btn
    # BTN opens far more than UTG.
    assert len(btn) > len(utg)
    # A clearly wide BTN-only offsuit hand:
    assert "K9o" in btn


def test_ranges_are_supersets_by_position():
    utg = opening_range("UTG")
    mp = opening_range("MP")
    co = opening_range("CO")
    btn = opening_range("BTN")
    assert utg <= mp <= co <= btn
