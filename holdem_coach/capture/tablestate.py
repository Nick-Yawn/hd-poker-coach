"""TableState — the per-frame structured snapshot (the new capture seam).

This is to the temporal tracker what HandHistory is to the analysis engine: a
clean, structured interface that insulates the fragile pixel-reading from the
reconstruction logic. The interpreter (interpret.py) produces one of these per
frame from OCR tokens (+ later, card-reader output); the hand tracker consumes a
stream of them to emit a HandHistory.

Pure data — no OCR, no pixels here.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SeatState:
    """What we observe at one occupied seat in a single frame."""

    name: str | None = None
    stack: float | None = None
    bet: float | None = None
    action: str | None = None  # fold/check/call/bet/raise/allin
    cx: float = 0.0            # screen position (fraction), for ordering seats
    cy: float = 0.0
    is_hero: bool = False
    has_cards: bool = False    # filled by the card reader later

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class TableState:
    """Everything read from one frame."""

    small_blind: float | None = None
    big_blind: float | None = None
    pot: float | None = None
    board: list[str] = field(default_factory=list)  # card reader fills this
    seats: list[SeatState] = field(default_factory=list)
    hero_name: str | None = None
    chat: list[str] = field(default_factory=list)

    @property
    def hero(self) -> SeatState | None:
        for s in self.seats:
            if s.is_hero:
                return s
        return None

    def seats_clockwise(self) -> list[SeatState]:
        """Seats ordered by screen angle around the table centroid.

        Useful for inferring betting order / positions once the button is known.
        """
        import math

        if not self.seats:
            return []
        cx = sum(s.cx for s in self.seats) / len(self.seats)
        cy = sum(s.cy for s in self.seats) / len(self.seats)
        return sorted(self.seats, key=lambda s: math.atan2(s.cy - cy, s.cx - cx))

    def to_dict(self) -> dict:
        return {
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "pot": self.pot,
            "board": self.board,
            "hero_name": self.hero_name,
            "seats": [s.to_dict() for s in self.seats],
            "chat": self.chat,
        }
