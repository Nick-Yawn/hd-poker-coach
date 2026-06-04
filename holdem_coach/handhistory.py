"""The HandHistory schema — the durable interface between capture and analysis.

This is the contract both halves of the app depend on (CLAUDE.md §5). Keep it
strict and validated. Implemented as dataclasses with explicit JSON
(de)serialization so the on-disk shape stays stable and reviewable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

RANKS = "23456789TJQKA"
SUITS = "cdhs"
STREETS = ("preflop", "flop", "turn", "river")
ACTIONS = ("post", "fold", "check", "call", "bet", "raise")
POSITIONS = ("UTG", "MP", "CO", "BTN", "SB", "BB", "UTG1", "UTG2", "HJ", "LJ")


class HandHistoryError(ValueError):
    """Raised when a HandHistory fails validation."""


def is_valid_card(card: str) -> bool:
    return (
        isinstance(card, str)
        and len(card) == 2
        and card[0] in RANKS
        and card[1] in SUITS
    )


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #
@dataclass
class TableInfo:
    max_seats: int
    small_blind: float
    big_blind: float

    @classmethod
    def from_dict(cls, d: dict) -> "TableInfo":
        return cls(
            max_seats=int(d["max_seats"]),
            small_blind=float(d["small_blind"]),
            big_blind=float(d["big_blind"]),
        )

    def to_dict(self) -> dict:
        return {
            "max_seats": self.max_seats,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
        }


@dataclass
class PlayerState:
    seat: int
    position: str
    starting_stack: float

    @classmethod
    def from_dict(cls, d: dict) -> "PlayerState":
        return cls(
            seat=int(d["seat"]),
            position=str(d["position"]),
            starting_stack=float(d["starting_stack"]),
        )

    def to_dict(self) -> dict:
        return {
            "seat": self.seat,
            "position": self.position,
            "starting_stack": self.starting_stack,
        }


@dataclass
class Board:
    flop: list[str] = field(default_factory=list)
    turn: str | None = None
    river: str | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> "Board":
        d = d or {}
        return cls(
            flop=list(d.get("flop", []) or []),
            turn=d.get("turn"),
            river=d.get("river"),
        )

    def to_dict(self) -> dict:
        return {"flop": self.flop, "turn": self.turn, "river": self.river}

    def cards_through(self, street: str) -> list[str]:
        """All board cards visible *at the start of* the given street."""
        cards: list[str] = []
        if street in ("flop", "turn", "river"):
            cards += list(self.flop)
        if street in ("turn", "river"):
            if self.turn:
                cards.append(self.turn)
        if street == "river":
            if self.river:
                cards.append(self.river)
        return cards

    def all_cards(self) -> list[str]:
        cards = list(self.flop)
        if self.turn:
            cards.append(self.turn)
        if self.river:
            cards.append(self.river)
        return cards


@dataclass
class Action:
    street: str
    seat: int
    action: str
    amount: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        return cls(
            street=str(d["street"]),
            seat=int(d["seat"]),
            action=str(d["action"]),
            amount=float(d.get("amount", 0) or 0),
        )

    def to_dict(self) -> dict:
        return {
            "street": self.street,
            "seat": self.seat,
            "action": self.action,
            "amount": self.amount,
        }


@dataclass
class Result:
    winning_seats: list[int]
    pot: float
    hero_net: float

    @classmethod
    def from_dict(cls, d: dict) -> "Result":
        return cls(
            winning_seats=[int(s) for s in d.get("winning_seats", [])],
            pot=float(d.get("pot", 0) or 0),
            hero_net=float(d.get("hero_net", 0) or 0),
        )

    def to_dict(self) -> dict:
        return {
            "winning_seats": self.winning_seats,
            "pot": self.pot,
            "hero_net": self.hero_net,
        }


@dataclass
class HandHistory:
    hand_id: str
    table: TableInfo
    hero_seat: int
    button_seat: int
    players: list[PlayerState]
    hero_hole_cards: list[str]
    board: Board
    actions: list[Action]
    result: Result

    # ---- (de)serialization ------------------------------------------------ #
    @classmethod
    def from_dict(cls, d: dict) -> "HandHistory":
        hh = cls(
            hand_id=str(d["hand_id"]),
            table=TableInfo.from_dict(d["table"]),
            hero_seat=int(d["hero_seat"]),
            button_seat=int(d["button_seat"]),
            players=[PlayerState.from_dict(p) for p in d["players"]],
            hero_hole_cards=list(d["hero_hole_cards"]),
            board=Board.from_dict(d.get("board")),
            actions=[Action.from_dict(a) for a in d.get("actions", [])],
            result=Result.from_dict(d.get("result", {})),
        )
        hh.validate()
        return hh

    def to_dict(self) -> dict:
        return {
            "hand_id": self.hand_id,
            "table": self.table.to_dict(),
            "hero_seat": self.hero_seat,
            "button_seat": self.button_seat,
            "players": [p.to_dict() for p in self.players],
            "hero_hole_cards": self.hero_hole_cards,
            "board": self.board.to_dict(),
            "actions": [a.to_dict() for a in self.actions],
            "result": self.result.to_dict(),
        }

    @classmethod
    def from_json(cls, text: str) -> "HandHistory":
        return cls.from_dict(json.loads(text))

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def load(cls, path: str | Path) -> "HandHistory":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json() + "\n", encoding="utf-8")

    # ---- convenience ------------------------------------------------------- #
    def seat_position(self, seat: int) -> str | None:
        for p in self.players:
            if p.seat == seat:
                return p.position
        return None

    @property
    def hero_position(self) -> str | None:
        return self.seat_position(self.hero_seat)

    # ---- validation -------------------------------------------------------- #
    def validate(self) -> "HandHistory":
        """Raise HandHistoryError if the record is internally inconsistent."""
        seats = {p.seat for p in self.players}
        if len(seats) != len(self.players):
            raise HandHistoryError("duplicate seat numbers in players")
        if self.hero_seat not in seats:
            raise HandHistoryError(
                f"hero_seat {self.hero_seat} is not among player seats {sorted(seats)}"
            )
        if self.button_seat not in seats:
            raise HandHistoryError(
                f"button_seat {self.button_seat} is not among player seats {sorted(seats)}"
            )

        for p in self.players:
            if p.position not in POSITIONS:
                raise HandHistoryError(
                    f"seat {p.seat} has unknown position {p.position!r}"
                )

        # Cards: notation + no duplicates across hole cards and board.
        all_cards = list(self.hero_hole_cards) + self.board.all_cards()
        for c in all_cards:
            if not is_valid_card(c):
                raise HandHistoryError(f"invalid card notation: {c!r}")
        if len(self.hero_hole_cards) != 2:
            raise HandHistoryError("hero must have exactly 2 hole cards")
        if self.board.flop and len(self.board.flop) != 3:
            raise HandHistoryError("flop must be empty or exactly 3 cards")
        if self.board.turn and not self.board.flop:
            raise HandHistoryError("turn present without a flop")
        if self.board.river and not self.board.turn:
            raise HandHistoryError("river present without a turn")
        if len(set(all_cards)) != len(all_cards):
            raise HandHistoryError(f"duplicate card(s) across hole cards/board: {all_cards}")

        # Actions.
        for a in self.actions:
            if a.street not in STREETS:
                raise HandHistoryError(f"unknown street {a.street!r}")
            if a.action not in ACTIONS:
                raise HandHistoryError(f"unknown action {a.action!r}")
            if a.seat not in seats:
                raise HandHistoryError(f"action references unknown seat {a.seat}")
            if a.amount < 0:
                raise HandHistoryError(f"negative action amount: {a.amount}")

        if self.table.big_blind <= 0 or self.table.small_blind < 0:
            raise HandHistoryError("blinds must be positive")
        return self
