from conftest import SAMPLE_DIR

from holdem_coach.analysis.scorer import score_hand
from holdem_coach.coaching.coach import CoachingNote, coach_decisions
from holdem_coach.handhistory import HandHistory


def test_mock_coaching_one_note_per_decision():
    hh = HandHistory.load(SAMPLE_DIR / "hand1_preflop_mistake.json")
    decisions = score_hand(hh, iterations=500, seed=1)
    notes = coach_decisions(decisions)  # mock backend (client=None)
    assert len(notes) == len(decisions)
    assert all(isinstance(n, CoachingNote) for n in notes)
    for n in notes:
        assert n.concept and n.explanation and n.takeaway


def test_mock_coaching_does_not_invent_numbers():
    # The mock must echo the engine's equity, never a different figure.
    hh = HandHistory.load(SAMPLE_DIR / "hand2_pot_odds.json")
    decisions = score_hand(hh, iterations=1000, seed=1)
    flop = next(
        d for d in decisions if d.street == "flop" and d.hero_action == "call"
    )
    note = coach_decisions([flop])[0]
    assert f"{flop.required_equity:.0%}" in note.explanation
