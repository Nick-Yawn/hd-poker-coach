"""Buffered producer-consumer capture: never drop a fast action.

The single-loop tracker blocks on the ~0.66s OCR, so anything that changes on the
table during that window is missed. Here a CAPTURE thread grabs at high FPS and
change-gates frames into a bounded queue (cheap, no OCR), while the CONSUMER
drains the queue, runs recognition, and feeds the tracker. The buffer absorbs
bursts (a fast all-in sequence) so every change is processed, just slightly
behind real time — which is fine, because output is post-hand anyway.

Reconciling with the tracker's stability gate: the producer only enqueues CHANGED
frames, so each distinct state arrives once. To still let the board confirm
across frames, the consumer RE-FEEDS the last recognized state whenever the queue
is briefly empty (the table is static) — so a settled board accumulates
confirmations, while an action burst streams distinct states (transient garbage
never confirms).
"""

from __future__ import annotations

import queue
import threading
import time


def run_buffered_tracker(
    window_substr: str,
    *,
    hero_name: str | None,
    on_hand,
    on_event=None,
    on_state=None,
    seconds: float | None = None,
    grab_interval: float = 0.05,   # ~20 fps capture
    max_queue: int = 120,
    confirm_frames: int = 3,
) -> int:
    """Drive the tracker from a buffered high-FPS capture thread."""
    from .changegate import ChangeGate
    from .grabber import WindowGrabber
    from .live import recognize_state
    from .tracker import HandTracker

    frames: "queue.Queue" = queue.Queue(maxsize=max_queue)
    stop = threading.Event()
    dropped = [0]

    # -- producer: grab + change-gate + enqueue (no OCR) -------------------- #
    def producer() -> None:
        gate = ChangeGate()
        try:
            with WindowGrabber(window_substr) as grabber:
                while not stop.is_set():
                    t0 = time.perf_counter()
                    try:
                        frame = grabber.grab()
                        if gate.changed(frame):
                            try:
                                frames.put_nowait((frame, time.monotonic()))
                            except queue.Full:
                                # Consumer fell behind; drop the oldest to stay
                                # current (logged — a drop risks a missed action).
                                try:
                                    frames.get_nowait()
                                    dropped[0] += 1
                                except queue.Empty:
                                    pass
                                try:
                                    frames.put_nowait((frame, time.monotonic()))
                                except queue.Full:
                                    pass
                    except RuntimeError:
                        time.sleep(0.3)  # window minimized/gone; back off
                    dt = time.perf_counter() - t0
                    if grab_interval - dt > 0:
                        stop.wait(grab_interval - dt)
        except Exception:
            stop.set()

    capture = threading.Thread(target=producer, daemon=True)
    capture.start()

    # -- consumer: recognize + drive the tracker --------------------------- #
    tracker = HandTracker(hero_name=hero_name, confirm_frames=confirm_frames)
    hands = 0
    last_state = None
    prev_in_hand = False
    prev_board_n = 0
    start = time.monotonic()
    try:
        while seconds is None or (time.monotonic() - start) < seconds:
            try:
                frame, _ = frames.get(timeout=0.1)
                last_state = recognize_state(frame, hero_name)
                if on_state is not None:
                    on_state(last_state)
            except queue.Empty:
                pass  # table static: fall through and re-feed last_state

            if last_state is None:
                continue
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
    finally:
        stop.set()
        capture.join(timeout=1.0)
    if dropped[0]:
        print(f"(buffer dropped {dropped[0]} frame(s) — consumer fell behind)")
    return hands
