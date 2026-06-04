"""Live hand tracking loop: capture -> recognize -> HandTracker -> hand record.

Glues the pieces into the real end-to-end flow. Two subtleties:

  - Frame-skip vs stability: the ChangeGate avoids re-OCRing static frames, but
    the tracker confirms the board across several observations. So we still feed
    the tracker EVERY loop — reusing the last recognized state when the frame is
    unchanged — and only re-run the (expensive) OCR on change. Static stretches
    cost nothing yet still let the tracker confirm; animation frames re-OCR and
    are rejected by the tracker's stability gate.

  - Output is POST-HAND only. The tracker emits a hand record only when the chat
    announces a winner, so the review prints after the hand resolves — never on
    the live table (CLAUDE.md §1).
"""

from __future__ import annotations

import time


def recognize_state(frame, hero_name):
    """Full per-frame recognition -> a TableState with board + hero cards set."""
    from .viewer import recognize

    _, state, board_located = recognize(frame, hero_name=hero_name)
    state.board = [c for c, _ in board_located]
    return state


def run_tracker(
    window_substr: str,
    *,
    hero_name: str | None,
    on_hand,
    on_event=None,
    seconds: float | None = None,
    confirm_frames: int = 3,
    loop_interval: float = 0.15,
    on_state=None,
) -> int:
    """Drive the tracker over the live window. Returns the number of hands seen.

    on_hand(record_dict) fires when a hand completes. on_event(kind, tracker)
    fires for 'hand-start' and 'street' transitions (for progress display).
    """
    from .changegate import ChangeGate
    from .grabber import WindowGrabber
    from .tracker import HandTracker

    gate = ChangeGate()
    tracker = HandTracker(hero_name=hero_name, confirm_frames=confirm_frames)
    last_state = None
    prev_in_hand = False
    prev_board_n = 0
    hands = 0
    start = time.monotonic()

    with WindowGrabber(window_substr) as grabber:
        while seconds is None or (time.monotonic() - start) < seconds:
            try:
                frame = grabber.grab()
                if gate.changed(frame):  # re-OCR only on change
                    last_state = recognize_state(frame, hero_name)
                    if on_state is not None:
                        on_state(last_state)
                if last_state is not None:
                    record = tracker.observe(last_state, time.monotonic())

                    if on_event is not None:
                        if tracker.in_hand and not prev_in_hand:
                            on_event("hand-start", tracker)
                        n = len(tracker.current_board)
                        if tracker.in_hand and n != prev_board_n and n in (3, 4, 5):
                            on_event("street", tracker)
                        prev_board_n = n if tracker.in_hand else 0
                        prev_in_hand = tracker.in_hand

                    if record is not None:
                        hands += 1
                        on_hand(record)
            except RuntimeError:
                # window minimized/closed or a transient grab error; back off.
                time.sleep(0.5)
            time.sleep(loop_interval)
    return hands
