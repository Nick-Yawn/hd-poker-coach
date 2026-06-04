"""Temporal hand tracker: a stream of per-frame TableStates -> HandHistory.

The keystone of the capture layer. It consumes one TableState per frame (with
board cards and chat populated) plus a timestamp, runs a small state machine over
the hand lifecycle, and emits a completed HandHistory once a hand resolves — the
same schema the M1 analysis + coaching engine consumes.

Design choices that keep it robust and testable:
  - PURE: no pixels, no OCR here. Driven by TableState objects, so it can be
    unit-tested with hand-authored frame sequences (like the M1 synthetic hands).
  - STABILITY GATING: the board only advances on a read confirmed across several
    frames, and impossible reads (>5 cards, shrinking board) are rejected — the
    validation step showed transitional/animation frames produce garbage.
  - CHAT AS ORACLE: hand end + winner + amount come from the chat feed
    ("NAME won N with X"), which we verified HD Poker logs reliably.
  - POSITIONS FROM BLINDS: the small-blind poster anchors the button (button is
    the seat before SB), so we need no dealer-button detection.

Action reconstruction (who bet/called/raised/folded, in order) is the noisiest
part; this is a first-pass from per-street committed-amount deltas + the action
labels HD Poker paints under players, and is expected to be tuned against live
recordings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .interpret import name_similarity
from .tablestate import TableState

# Seats-from-button (clockwise) -> position name, by player count.
_POSITIONS = {
    2: ["BTN", "BB"],
    3: ["BTN", "SB", "BB"],
    4: ["BTN", "SB", "BB", "UTG"],
    5: ["BTN", "SB", "BB", "UTG", "CO"],
    6: ["BTN", "SB", "BB", "UTG", "HJ", "CO"],
    7: ["BTN", "SB", "BB", "UTG", "MP", "HJ", "CO"],
    8: ["BTN", "SB", "BB", "UTG", "UTG1", "MP", "HJ", "CO"],
    9: ["BTN", "SB", "BB", "UTG", "UTG1", "MP", "LJ", "HJ", "CO"],
}

_STREETS = ("preflop", "flop", "turn", "river")
_WON_RE = re.compile(r"(\w[\w]*)\s+won\s+([\d.,]+\s*[KMB]?)", re.I)


def _board_street(n_cards: int) -> str | None:
    return {0: "preflop", 3: "flop", 4: "turn", 5: "river"}.get(n_cards)


@dataclass
class _Player:
    seat: int
    name: str
    starting_stack: float
    cx: float
    cy: float
    is_hero: bool
    position: str | None = None


@dataclass
class _Hand:
    """Accumulator for the hand currently in progress."""

    small_blind: float
    big_blind: float
    players: list[_Player]
    hero_name: str | None
    board: list[str] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    street: str = "preflop"
    hero_hole_cards: list[str] | None = None
    # committed[street][name] = chips that seat has put in this street so far
    committed: dict = field(default_factory=lambda: {"preflop": {}})

    def player_by_name(self, name: str) -> _Player | None:
        best, score = None, 0.0
        for p in self.players:
            s = name_similarity(p.name, name)
            if s > score:
                best, score = p, s
        return best if score >= 0.6 else None


class HandTracker:
    """Feed TableStates with observe(); get a HandHistory back when a hand ends."""

    def __init__(self, *, hero_name: str | None = None, confirm_frames: int = 2,
                 max_seats: int = 9):
        self.hero_name = hero_name
        self.confirm_frames = confirm_frames
        self.max_seats = max_seats
        self._hand: _Hand | None = None
        self._hand_count = 0
        # debounce state for the board reading
        self._cand_board: list[str] = []
        self._cand_count = 0
        self._seen_chat: set[str] = set()

    # -- public ------------------------------------------------------------- #
    @property
    def in_hand(self) -> bool:
        return self._hand is not None

    @property
    def current_street(self) -> str | None:
        return self._hand.street if self._hand else None

    @property
    def current_board(self) -> list[str]:
        return list(self._hand.board) if self._hand else []

    def observe(self, state: TableState, t: float = 0.0) -> dict | None:
        """Ingest one frame. Returns a hand record (HandHistory-shaped dict) iff a
        hand just completed, else None.

        The dict validates into a HandHistory via ``HandHistory.from_dict`` once
        the hero's hole cards are present; until hole-card reading lands they are
        a ``["??", "??"]`` placeholder and the draft is inspectable but unvalidated.
        """
        board = self._stable_board(state.board)

        if self._hand is None:
            self._maybe_start_hand(state, board)
            return None

        # Robustness: a confirmed EMPTY board after we'd reached a flop+ means the
        # previous hand ended (we likely missed the chat 'won'). Drop the stuck
        # hand and let a fresh one start, so a missed end can't wedge the tracker.
        if board is not None and len(board) == 0 and len(self._hand.board) >= 3:
            self._hand = None
            self._maybe_start_hand(state, board)
            return None

        self._apply_to_hand(state, board)

        finished = self._check_hand_end(state)
        if finished is not None:
            self._hand = None
            return finished
        return None

    # -- stability gating --------------------------------------------------- #
    def _stable_board(self, raw: list[str]) -> list[str] | None:
        """Return a board reading only once it's been seen confirm_frames times.

        Rejects impossible reads (more than 5 cards). Returns None until a
        reading is confirmed; the last confirmed board persists in the hand.
        """
        if raw is None or len(raw) > 5:
            return None
        if raw == self._cand_board:
            self._cand_count += 1
        else:
            self._cand_board = list(raw)
            self._cand_count = 1
        if self._cand_count >= self.confirm_frames:
            return list(self._cand_board)
        return None

    # -- lifecycle ---------------------------------------------------------- #
    def _maybe_start_hand(self, state: TableState, board: list[str] | None) -> None:
        # A new hand begins at confirmed preflop (empty board) with the big blind
        # posted. We anchor on the BB alone — it's the larger, more reliably-read
        # pill, and it fixes every position (button = 2 seats before BB) without
        # needing to also catch the small blind in the same frame.
        if board is None or len(board) != 0:
            return
        if not state.big_blind:
            return
        posters = [s for s in state.seats if s.bet and s.bet > 0]
        bb = next((s for s in posters if _close(s.bet, state.big_blind)), None)
        if bb is None:
            return
        sb = next((s for s in posters if _close(s.bet, state.small_blind)), None)

        players = self._roster(state)
        if len(players) < 2:
            return
        self._assign_positions(players, bb_name=bb.name)

        hand = _Hand(
            small_blind=state.small_blind,
            big_blind=state.big_blind,
            players=players,
            hero_name=self.hero_name,
        )
        # Record the blind posts as actions.
        for s in (sb, bb):
            p = hand.player_by_name(s.name)
            if p:
                hand.actions.append(
                    {"street": "preflop", "seat": p.seat, "action": "post", "amount": s.bet}
                )
                hand.committed["preflop"][p.name] = s.bet
        self._hand = hand
        # The chat feed still shows PREVIOUS hands' "won" lines. Mark everything
        # currently visible as seen so only a genuinely new win ends THIS hand.
        self._seen_chat.update(state.chat)

    def _roster(self, state: TableState) -> list[_Player]:
        """Seats with a known stack become players, numbered clockwise."""
        seats = [s for s in state.seats if s.name and s.stack is not None]
        ordered = _clockwise(seats)
        players = []
        for i, s in enumerate(ordered, start=1):
            players.append(
                _Player(seat=i, name=s.name, starting_stack=s.stack,
                        cx=s.cx, cy=s.cy, is_hero=bool(s.is_hero))
            )
        return players

    def _assign_positions(self, players: list[_Player], *, bb_name) -> None:
        n = len(players)
        names = _POSITIONS.get(n)
        if not names:
            return
        # players are clockwise; find BB, then walk back to the button. Heads-up
        # the button is the SB (1 before BB); otherwise it's 2 before BB.
        order = players  # already clockwise by _roster
        bb_idx = max(range(n), key=lambda i: name_similarity(order[i].name, bb_name))
        button_idx = (bb_idx - (1 if n == 2 else 2)) % n
        for offset in range(n):
            p = order[(button_idx + offset) % n]
            p.position = names[offset]

    def _apply_to_hand(self, state: TableState, board: list[str] | None) -> None:
        hand = self._hand
        assert hand is not None

        # Capture the hero's hole cards the first time we can read them.
        if hand.hero_hole_cards is None:
            hero = next((s for s in state.seats if s.is_hero and s.hole_cards), None)
            if hero and len(hero.hole_cards) == 2:
                hand.hero_hole_cards = list(hero.hole_cards)

        # Advance the board only forward (never shrink on a bad frame).
        if board is not None and len(board) > len(hand.board) and len(board) in (3, 4, 5):
            hand.board = list(board)
            hand.street = _board_street(len(board)) or hand.street
            hand.committed.setdefault(hand.street, {})

        # Reconstruct actions from per-street committed-amount deltas + labels.
        street = hand.street
        committed = hand.committed.setdefault(street, {})
        for s in state.seats:
            p = hand.player_by_name(s.name) if s.name else None
            if p is None:
                continue
            if s.action == "fold":
                if not _last_is(hand, p.seat, street, "fold"):
                    hand.actions.append(
                        {"street": street, "seat": p.seat, "action": "fold", "amount": 0}
                    )
                continue
            bet = s.bet or 0.0
            prev = committed.get(p.name, 0.0)
            if bet > prev + 1e-9:
                delta = bet - prev
                committed[p.name] = bet
                action = s.action or _infer_action(committed, p.name, bet)
                hand.actions.append(
                    {"street": street, "seat": p.seat, "action": action, "amount": delta}
                )
            elif s.action == "check" and not _last_is(hand, p.seat, street, "check"):
                hand.actions.append(
                    {"street": street, "seat": p.seat, "action": "check", "amount": 0}
                )

    def _check_hand_end(self, state: TableState) -> HandHistory | None:
        for line in state.chat:
            if line in self._seen_chat:
                continue
            m = _WON_RE.search(line)
            if m:
                self._seen_chat.add(line)
                return self._finalize(winner_name=m.group(1), won_text=m.group(2))
        return None

    # -- build the HandHistory ---------------------------------------------- #
    def _finalize(self, *, winner_name: str, won_text: str) -> dict:
        from .interpret import parse_amount

        hand = self._hand
        assert hand is not None
        self._hand_count += 1

        winner = hand.player_by_name(winner_name)
        won = parse_amount(won_text.replace(" ", "")) or 0.0
        # Prefer the chat-reported amount as the pot; fall back to summing actions
        # only if the chat amount didn't parse (action sums are noisy live).
        pot = won if won > 0 else sum(a["amount"] for a in hand.actions)

        hero = next((p for p in hand.players if p.is_hero), None)
        hero_contrib = sum(
            a["amount"] for a in hand.actions
            if hero and a["seat"] == hero.seat and a["action"] != "fold"
        )
        hero_net = 0.0
        if hero is not None:
            if winner and winner.seat == hero.seat:
                hero_net = won - hero_contrib  # collected the pot
            else:
                hero_net = -hero_contrib

        button = next((p for p in hand.players if p.position == "BTN"), None)
        flop = hand.board[0:3]
        d = {
            "hand_id": f"live-{self._hand_count:04d}",
            "table": {
                "max_seats": self.max_seats,
                "small_blind": hand.small_blind,
                "big_blind": hand.big_blind,
            },
            "hero_seat": hero.seat if hero else hand.players[0].seat,
            "button_seat": button.seat if button else hand.players[0].seat,
            "players": [
                {"seat": p.seat, "position": p.position or "BTN",
                 "starting_stack": p.starting_stack}
                for p in hand.players
            ],
            # Real cards once hole-card reading lands; placeholder otherwise so
            # the draft is still inspectable (won't pass HandHistory validation).
            "hero_hole_cards": hand.hero_hole_cards or ["??", "??"],
            "board": {
                "flop": flop if len(hand.board) >= 3 else [],
                "turn": hand.board[3] if len(hand.board) >= 4 else None,
                "river": hand.board[4] if len(hand.board) >= 5 else None,
            },
            "actions": hand.actions,
            "result": {
                "winning_seats": [winner.seat] if winner else [],
                "pot": pot,
                "hero_net": hero_net,
            },
        }
        return d  # NOTE: dict for now; see observe() callers / tests


def _close(a: float | None, b: float | None, *, tol: float = 0.01) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tol * max(1.0, abs(b))


def _clockwise(seats):
    """Order seats clockwise around their centroid (screen angle)."""
    import math

    if not seats:
        return []
    cx = sum(s.cx for s in seats) / len(seats)
    cy = sum(s.cy for s in seats) / len(seats)
    return sorted(seats, key=lambda s: math.atan2(s.cy - cy, s.cx - cx))


def _last_is(hand: _Hand, seat: int, street: str, action: str) -> bool:
    for a in reversed(hand.actions):
        if a["seat"] == seat and a["street"] == street:
            return a["action"] == action
    return False


def _infer_action(committed: dict, name: str, bet: float) -> str:
    others = [v for k, v in committed.items() if k != name]
    high = max(others) if others else 0.0
    if high <= 0:
        return "bet"
    return "call" if _close(bet, high) else "raise"
