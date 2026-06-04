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
