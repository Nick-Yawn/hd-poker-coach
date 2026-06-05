"""Temporal tracker tests, driven by hand-authored frame sequences.

Like the M1 synthetic hands, these exercise the tracker logic with no pixels:
build TableStates frame by frame, feed them to HandTracker.observe, and assert
on the emitted hand record (which must validate into a HandHistory the M1 engine
can analyze).
"""

from holdem_coach.capture.tablestate import SeatState, TableState
from holdem_coach.capture.tracker import HandTracker
from holdem_coach.handhistory import HandHistory

# Six seats around the table (clockwise screen positions): top row left->right,
# bottom row left->right. Stable cx/cy so the tracker can order them.
SEAT_POS = {
    "alice": (0.30, 0.20),   # top-left
    "bob": (0.50, 0.18),     # top-center
    "carol": (0.70, 0.20),   # top-right
    "dave": (0.70, 0.80),    # bottom-right
    "hero": (0.50, 0.82),    # bottom-center (our hero)
    "frank": (0.30, 0.80),   # bottom-left
}
STACKS = {n: 1000.0 for n in SEAT_POS}


def _seat(name, *, stack=None, bet=0.0, action=None, hole=None):
    cx, cy = SEAT_POS[name]
    return SeatState(
        name=name, stack=stack if stack is not None else STACKS[name],
        bet=bet, action=action, cx=cx, cy=cy,
        is_hero=(name == "hero"), hole_cards=hole,
    )


def _state(seats, *, board=None, chat=None):
    return TableState(
        small_blind=5.0, big_blind=10.0, board=board or [],
        seats=seats, hero_name="hero", chat=chat or [],
    )


def _run_synthetic_hand(confirm_frames=2):
    """A full hand: hero (BTN-ish) plays, alice wins at showdown.

    Seat order clockwise from _clockwise(): alice, carol, dave, hero, frank, bob
    by angle — positions are derived from the blind posters below.
    """
    tracker = HandTracker(hero_name="hero", confirm_frames=confirm_frames, max_seats=9)
    out = None

    def feed(seats, **kw):
        nonlocal out
        # Repeat each frame confirm_frames times so the board reading confirms.
        for _ in range(confirm_frames):
            r = tracker.observe(_state(seats, **kw))
            if r:
                out = r

    # PREFLOP: frank posts SB(5), alice posts BB(10); hero has cards.
    feed([
        _seat("frank", bet=5.0), _seat("alice", bet=10.0),
        _seat("bob"), _seat("carol"), _seat("dave"),
        _seat("hero", hole=["Ah", "Kd"]),
    ])
    # hero raises to 30, alice calls 20 more (to 30).
    feed([
        _seat("frank", bet=5.0), _seat("alice", bet=10.0),
        _seat("bob", action="fold"), _seat("carol", action="fold"),
        _seat("dave", action="fold"),
        _seat("hero", bet=30.0, action="raise", hole=["Ah", "Kd"]),
    ])
    feed([
        _seat("frank", action="fold"), _seat("alice", bet=30.0, action="call"),
        _seat("hero", bet=30.0, hole=["Ah", "Kd"]),
    ])
    # FLOP
    feed([
        _seat("alice", bet=0.0), _seat("hero", bet=0.0, hole=["Ah", "Kd"]),
    ], board=["7c", "2d", "Ts"])
    feed([
        _seat("alice", action="check"),
        _seat("hero", bet=40.0, action="bet", hole=["Ah", "Kd"]),
    ], board=["7c", "2d", "Ts"])
    feed([
        _seat("alice", bet=40.0, action="call"),
        _seat("hero", bet=40.0, hole=["Ah", "Kd"]),
    ], board=["7c", "2d", "Ts"])
    # TURN, RIVER (checked through)
    feed([_seat("alice"), _seat("hero", hole=["Ah", "Kd"])],
         board=["7c", "2d", "Ts", "Qh"])
    feed([_seat("alice"), _seat("hero", hole=["Ah", "Kd"])],
         board=["7c", "2d", "Ts", "Qh", "3s"])
    # Showdown: chat announces the winner -> hand ends.
    feed([_seat("alice"), _seat("hero", hole=["Ah", "Kd"])],
         board=["7c", "2d", "Ts", "Qh", "3s"],
         chat=["3:01 PM alice won 150 with Two Pair"])
    return out


def test_tracker_emits_a_hand_record():
    rec = _run_synthetic_hand()
    assert rec is not None
    assert rec["table"]["small_blind"] == 5.0
    assert rec["table"]["big_blind"] == 10.0


def test_tracker_record_validates_as_handhistory():
    rec = _run_synthetic_hand()
    hh = HandHistory.from_dict(rec)  # validates: cards, seats, actions, etc.
    assert hh.hero_hole_cards == ["Ah", "Kd"]


def test_tracker_reconstructs_full_board():
    rec = _run_synthetic_hand()
    assert rec["board"]["flop"] == ["7c", "2d", "Ts"]
    assert rec["board"]["turn"] == "Qh"
    assert rec["board"]["river"] == "3s"


def test_tracker_derives_positions_from_blinds():
    rec = _run_synthetic_hand()
    pos = {p["seat"]: p["position"] for p in rec["players"]}
    seat_of = {p["seat"]: None for p in rec["players"]}
    # frank posted SB, alice posted BB -> those positions must be assigned.
    positions = set(pos.values())
    assert "SB" in positions and "BB" in positions and "BTN" in positions


def test_tracker_records_blind_posts_and_actions():
    rec = _run_synthetic_hand()
    actions = rec["actions"]
    kinds = {(a["action"]) for a in actions}
    assert "post" in kinds            # blinds recorded
    assert "raise" in kinds           # hero's preflop raise
    assert "bet" in kinds             # hero's flop bet
    # Two posts (SB + BB).
    assert sum(1 for a in actions if a["action"] == "post") == 2


def test_tracker_result_from_chat():
    rec = _run_synthetic_hand()
    assert rec["result"]["pot"] > 0
    # alice won; hero did not -> hero_net should be negative (hero put chips in).
    assert rec["result"]["hero_net"] < 0


def test_tracker_output_feeds_m1_analysis_and_coaching():
    # The whole point: a tracked hand flows into the M1 engine + coaching.
    from holdem_coach.analysis.scorer import score_hand
    from holdem_coach.coaching.coach import coach_decisions

    rec = _run_synthetic_hand()
    hh = HandHistory.from_dict(rec)
    decisions = score_hand(hh, iterations=500, seed=1)
    assert decisions, "expected hero decisions to score"
    assert all(0.0 <= d.equity <= 1.0 for d in decisions)
    notes = coach_decisions(decisions)  # mocked backend
    assert len(notes) == len(decisions)


def test_tracker_starts_hand_with_only_big_blind_read():
    # Live, we often catch only the BB pill. Hand-start must work (and not crash)
    # when the SB wasn't read.
    tracker = HandTracker(hero_name="hero", confirm_frames=1)
    seats = [
        _seat("alice", bet=10.0),  # BB only; no SB bet present
        _seat("bob"), _seat("carol"),
        _seat("hero", hole=["Ah", "Kd"]),
    ]
    tracker.observe(_state(seats))
    assert tracker.in_hand is True
    # BB recorded as a post; no crash on the missing SB.
    posts = [a for a in tracker._hand.actions if a["action"] == "post"]
    assert len(posts) == 1


def test_tracker_rejects_implausible_board():
    # A frame reading 6+ "cards" (animation garble) must not advance the board.
    tracker = HandTracker(hero_name="hero", confirm_frames=1)
    # start a hand
    tracker.observe(_state([
        _seat("frank", bet=5.0), _seat("alice", bet=10.0),
        _seat("hero", hole=["Ah", "Kd"]), _seat("bob"),
    ]))
    junk = ["Ks", "Kc", "Kd", "Kh", "Qc", "Qd", "Qh", "Js"]
    tracker.observe(_state([_seat("alice"), _seat("hero", hole=["Ah", "Kd"])],
                           board=junk))
    # No emission, no crash; board stays empty/preflop.
    assert tracker._hand is not None
    assert tracker._hand.board == []
