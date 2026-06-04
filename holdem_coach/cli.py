"""CLI entry point: post-hand review printer (CLAUDE.md §8 task 7).

    python -m holdem_coach analyze sample_hands/hand1.json

Loads a HandHistory, runs the deterministic analysis engine, runs the (mocked)
coaching layer, and prints a readable review. This is post-hand output only —
it never runs against a live, unresolved hand.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analysis.scorer import score_hand
from .coaching.coach import coach_decisions, make_anthropic_client
from .handhistory import HandHistory, HandHistoryError

_BAR = "─" * 60


def _fmt_board(cards: list[str]) -> str:
    return " ".join(cards) if cards else "(preflop)"


def render_review(
    hh: HandHistory, *, iterations: int, seed: int | None, use_llm: bool = False
) -> str:
    decisions = score_hand(hh, iterations=iterations, seed=seed)
    client = make_anthropic_client() if use_llm else None
    notes = coach_decisions(decisions, client=client)  # mocked unless --llm

    lines: list[str] = []
    lines.append(_BAR)
    lines.append(f"POST-HAND REVIEW  ·  {hh.hand_id}")
    lines.append(
        f"Hero: seat {hh.hero_seat} ({hh.hero_position})  "
        f"{' '.join(hh.hero_hole_cards)}   "
        f"Table: {hh.table.max_seats}-max  "
        f"blinds {hh.table.small_blind:g}/{hh.table.big_blind:g}"
    )
    board = hh.board.all_cards()
    if board:
        lines.append(f"Board: {_fmt_board(board)}")
    lines.append(
        f"Result: pot {hh.result.pot:g}, hero net "
        f"{hh.result.hero_net:+g}  (winners: seats {hh.result.winning_seats})"
    )
    lines.append(_BAR)

    if not decisions:
        lines.append("No hero decisions found in this hand.")
        return "\n".join(lines)

    leaks = 0
    for i, (d, note) in enumerate(zip(decisions, notes), start=1):
        marker = {"LEAK": "✗", "OK": "✓", "THIN": "≈", "INFO": "·"}.get(d.tag, "·")
        if d.leak:
            leaks += 1
        lines.append("")
        lines.append(
            f"[{i}] {marker} {d.street.upper()}  "
            f"board {_fmt_board(d.board)}  ·  {d.hero_class}"
        )
        action_line = f"    action: {d.hero_action}"
        if d.hero_amount:
            action_line += f" {d.hero_amount:g}"
        lines.append(action_line)

        nums = [f"equity ~{d.equity:.0%} (vs {d.villain_desc})"]
        if d.facing_bet:
            nums.append(
                f"to call {d.to_call:g} into {d.pot_before:g} "
                f"→ need {d.required_equity:.0%}"
            )
            if d.ev_call is not None:
                nums.append(f"EV(call) {d.ev_call:+.2f}")
        lines.append("    " + "  |  ".join(nums))
        lines.append(f"    baseline: {d.baseline}")
        lines.append(f"    coach [{note.concept}]: {note.explanation}")
        lines.append(f"    takeaway: {note.takeaway}")

    lines.append("")
    lines.append(_BAR)
    verdict = (
        f"{leaks} leak(s) flagged."
        if leaks
        else "No clear leaks — standard line."
    )
    lines.append(f"SUMMARY: {len(decisions)} hero decision(s).  {verdict}")
    lines.append(_BAR)
    return "\n".join(lines)


def _run_track(args) -> int:
    """Live loop: print a post-hand review whenever a hand completes."""
    from .capture.live import run_tracker

    def on_event(kind, tracker):
        if kind == "hand-start":
            print("\n● new hand…", flush=True)
        elif kind == "street":
            board = tracker.current_board
            if board:
                print(f"   {tracker.current_street}: {' '.join(board)}", flush=True)

    def on_hand(record):
        try:
            hh = HandHistory.from_dict(record)
        except HandHistoryError as e:
            print(f"\n[{record['hand_id']}] hand ended but couldn't build a full "
                  f"review ({e}).", file=sys.stderr)
            print(f"   board={record['board']}  actions={len(record['actions'])}  "
                  f"result={record['result']}", file=sys.stderr)
            return
        try:
            review = render_review(
                hh, iterations=args.iterations, seed=args.seed, use_llm=args.llm
            )
        except RuntimeError as e:  # e.g. missing API key for --llm
            print(f"error: {e}", file=sys.stderr)
            return
        print("\n" + review, flush=True)

    seen_chat: set[str] = set()

    def on_state(state):
        for line in state.chat:
            if line not in seen_chat:
                seen_chat.add(line)
                print(f"   chat» {line}", flush=True)
        bets = {s.name: s.bet for s in state.seats if s.bet}
        blinds = f"{state.small_blind}/{state.big_blind}"
        print(f"   [state] blinds={blinds} board={state.board} bets={bets}",
              flush=True)

    print(
        f"Tracking '{args.window}' as {args.hero!r}. Post-hand reviews print here "
        "when each hand ends. Ctrl+C to stop.",
        flush=True,
    )
    try:
        n = run_tracker(
            args.window, hero_name=args.hero, on_hand=on_hand, on_event=on_event,
            seconds=args.seconds, on_state=on_state if args.debug else None,
        )
    except KeyboardInterrupt:
        n = None
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if n is not None:
        print(f"\nStopped. {n} hand(s) reviewed.")
    return 0


def _run_capture(args) -> int:
    """Handle the capture subcommands (windows / snapshot / record)."""
    from .capture import list_windows

    if args.command == "windows":
        wins = list_windows()
        if args.filter:
            needle = args.filter.lower()
            wins = [w for w in wins if needle in w.title.lower()]
        if not wins:
            print("no matching windows.", file=sys.stderr)
            return 1
        print(f"{'SIZE':>11}   TITLE")
        for w in wins:
            print(f"{w.width:>4}x{w.height:<4}   {w.title}")
        return 0

    try:
        if args.command == "snapshot":
            from .capture.grabber import MonitorGrabber, WindowGrabber
            from .capture.recorder import save_frame

            if args.monitor is not None:
                grabber = MonitorGrabber(args.monitor)
            elif args.window:
                grabber = WindowGrabber(args.window, client=not args.full_window)
            else:
                print("error: pass --window <title> or --monitor <n>", file=sys.stderr)
                return 2
            with grabber:
                path = save_frame(grabber.grab(), args.out)
            print(f"saved {path}")
            return 0

        if args.command == "calibrate":
            import cv2

            from .capture.layout import DEFAULT_6MAX, annotate

            if args.in_path:
                frame = cv2.imread(str(args.in_path))
                if frame is None:
                    print(f"error: could not read {args.in_path}", file=sys.stderr)
                    return 2
            elif args.window:
                from .capture.grabber import WindowGrabber

                with WindowGrabber(args.window) as g:
                    frame = g.grab()
            else:
                print("error: pass --in <png> or --window <title>", file=sys.stderr)
                return 2
            from .capture.recorder import save_frame

            save_frame(annotate(frame, DEFAULT_6MAX), args.out)
            print(f"saved {args.out}")
            return 0

        if args.command == "ocr":
            import cv2

            from .capture.interpret import interpret
            from .capture.ocr import read_tokens
            from .capture.recorder import save_frame

            if args.in_path:
                frame = cv2.imread(str(args.in_path))
                if frame is None:
                    print(f"error: could not read {args.in_path}", file=sys.stderr)
                    return 2
            elif args.window:
                from .capture.grabber import WindowGrabber

                with WindowGrabber(args.window) as g:
                    frame = g.grab()
            else:
                print("error: pass --in <png> or --window <title>", file=sys.stderr)
                return 2

            tokens = read_tokens(frame)
            state = interpret(tokens, hero_name=args.hero)
            print(f"stakes: {state.small_blind}/{state.big_blind}  pot: {state.pot}")
            print(f"seats ({len(state.seats)}):")
            for s in sorted(state.seats, key=lambda s: (s.cy, s.cx)):
                tag = "  <- HERO" if s.is_hero else ""
                print(f"  {str(s.name):<14} stack={s.stack} action={s.action}{tag}")

            h, w = frame.shape[:2]
            vis = frame.copy()
            for t in tokens:
                x0, y0 = int(t.left * w), int(t.top * h)
                x1, y1 = int(t.right * w), int(t.bottom * h)
                cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 255, 0), 1)
            save_frame(vis, args.out)
            print(f"overlay -> {args.out}")
            return 0

        if args.command == "overlay":
            from .capture.overlay import run_overlay

            print(
                "Overlay: detections only (no advice). "
                "Close with Ctrl+C here, or --seconds."
            )
            n = run_overlay(args.window, hero_name=args.hero, seconds=args.seconds)
            print(f"overlay ran {n} tick(s)")
            return 0

        if args.command == "watch":
            from .capture.viewer import run_viewer

            n = run_viewer(
                args.window, hero_name=args.hero, scale=args.scale,
                frames=args.frames, show=not args.no_show,
                save_path=str(args.save) if args.save else None,
            )
            print(f"watched {n} frame(s)")
            return 0

        if args.command == "record":
            from .capture.grabber import WindowGrabber
            from .capture.recorder import record

            grabber = WindowGrabber(args.window, client=not args.full_window)
            target = args.count if args.count else "∞ (Ctrl+C to stop)"
            print(
                f"recording {target} frames every {args.interval:g}s "
                f"from window ~{args.window!r} → {args.out}/"
            )
            with grabber:
                n = record(
                    grabber, args.out, interval=args.interval, count=args.count,
                    on_save=lambda i, p: print(f"  [{i + 1}] {p.name}"),
                )
            print(f"done — {n} frame(s) written to {args.out}/")
            return 0
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="holdem-coach",
        description="Post-hand Texas Hold'em study coach (HD Poker, play money).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_an = sub.add_parser("analyze", help="analyze a HandHistory JSON file")
    p_an.add_argument("path", type=Path, help="path to a HandHistory .json file")
    p_an.add_argument(
        "--iterations", type=int, default=8000,
        help="Monte Carlo iterations for equity (default 8000)",
    )
    p_an.add_argument(
        "--seed", type=int, default=1234,
        help="RNG seed for reproducible equity (default 1234)",
    )
    p_an.add_argument(
        "--llm", action="store_true",
        help="use real Anthropic coaching instead of the mock "
        "(requires ANTHROPIC_API_KEY and the [coaching] extra)",
    )

    sub.add_parser("gui", help="launch the desktop review panel")

    # --- capture (Milestone 2 vision) ------------------------------------- #
    p_win = sub.add_parser("windows", help="list visible windows (find HD Poker)")
    p_win.add_argument(
        "--filter", default="", help="only show windows whose title contains this"
    )

    p_snap = sub.add_parser("snapshot", help="save one frame from a window/monitor")
    p_snap.add_argument("--window", help="capture the window whose title contains this")
    p_snap.add_argument("--monitor", type=int, help="capture this monitor (0=all)")
    p_snap.add_argument(
        "--out", type=Path, default=Path("captures/snapshot.png"),
        help="output PNG path (default captures/snapshot.png)",
    )
    p_snap.add_argument(
        "--full-window", action="store_true",
        help="capture the whole window incl. title bar (default: client area only)",
    )

    p_cal = sub.add_parser(
        "calibrate", help="overlay the table layout regions on a frame"
    )
    p_cal.add_argument("--in", dest="in_path", type=Path, help="input PNG frame")
    p_cal.add_argument("--window", help="or grab live from this window")
    p_cal.add_argument(
        "--out", type=Path, default=Path("captures/_calibrated.png"),
        help="annotated output PNG (default captures/_calibrated.png)",
    )

    p_ocr = sub.add_parser("ocr", help="run OCR on a frame and dump tokens + overlay")
    p_ocr.add_argument("--in", dest="in_path", type=Path, help="input PNG frame")
    p_ocr.add_argument("--window", help="or grab live from this window")
    p_ocr.add_argument("--hero", help="hero username (for seat detection)")
    p_ocr.add_argument(
        "--out", type=Path, default=Path("captures/_ocr.png"),
        help="annotated output PNG (default captures/_ocr.png)",
    )

    p_watch = sub.add_parser(
        "watch", help="live recognizer view in a separate window (debug)"
    )
    p_watch.add_argument("--window", default="HD Poker", help="window title substring")
    p_watch.add_argument("--hero", help="hero username (for seat detection)")
    p_watch.add_argument("--scale", type=float, default=0.6, help="display scale")
    p_watch.add_argument("--frames", type=int, help="stop after N frames (default: until Q)")
    p_watch.add_argument(
        "--save", type=Path, help="write the last annotated frame here (headless check)"
    )
    p_watch.add_argument("--no-show", action="store_true", help="don't open a window")

    p_track = sub.add_parser(
        "track", help="live: capture -> tracker -> post-hand review per hand"
    )
    p_track.add_argument("--window", default="HD Poker", help="window title substring")
    p_track.add_argument("--hero", required=True, help="your username (for hero seat)")
    p_track.add_argument("--seconds", type=float, help="stop after N seconds")
    p_track.add_argument("--iterations", type=int, default=4000, help="equity MC iters")
    p_track.add_argument("--seed", type=int, default=1234, help="equity RNG seed")
    p_track.add_argument("--llm", action="store_true", help="real Anthropic coaching")
    p_track.add_argument("--debug", action="store_true",
                         help="log the live recognition stream (chat, blinds, bets)")

    p_over = sub.add_parser(
        "overlay", help="transparent on-table overlay of detections (click-through)"
    )
    p_over.add_argument("--window", default="HD Poker", help="window title substring")
    p_over.add_argument("--hero", help="hero username (for seat detection)")
    p_over.add_argument("--seconds", type=float, help="auto-close after N seconds")

    p_rec = sub.add_parser("record", help="save frames at an interval for dev data")
    p_rec.add_argument("--window", required=True, help="title substring to capture")
    p_rec.add_argument("--out", type=Path, default=Path("captures"), help="output dir")
    p_rec.add_argument("--interval", type=float, default=1.0, help="seconds between frames")
    p_rec.add_argument("--count", type=int, help="number of frames (default: until Ctrl+C)")
    p_rec.add_argument(
        "--full-window", action="store_true",
        help="capture the whole window incl. title bar (default: client area only)",
    )

    args = parser.parse_args(argv)

    # The review uses box-drawing/check glyphs; the default Windows console code
    # page (cp1252) can't encode them. Prefer UTF-8 where the stream supports it.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass

    if args.command == "gui":
        from .app import main as gui_main

        return gui_main()

    if args.command == "track":
        return _run_track(args)

    if args.command in (
        "windows", "snapshot", "record", "calibrate", "ocr", "watch", "overlay",
    ):
        return _run_capture(args)

    if args.command == "analyze":
        try:
            hh = HandHistory.load(args.path)
        except FileNotFoundError:
            print(f"error: no such file: {args.path}", file=sys.stderr)
            return 2
        except HandHistoryError as e:
            print(f"error: invalid hand history: {e}", file=sys.stderr)
            return 2
        try:
            review = render_review(
                hh, iterations=args.iterations, seed=args.seed, use_llm=args.llm
            )
        except RuntimeError as e:  # e.g. missing API key / SDK for --llm
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(review)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
