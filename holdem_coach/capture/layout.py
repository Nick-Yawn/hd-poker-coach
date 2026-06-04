"""Resize-tolerant, seat-agnostic table layout.

Everything is a fraction of the client area [0, 1], so one layout works at any
window size — multiply by the current width/height. HD Poker does NOT rotate the
view to seat the hero at the bottom: the hero can be ANY of the six fixed screen
seats (user-confirmed). So seats are fixed screen positions, and which one is the
hero is resolved at runtime (by matching the known username; the hero's cards
being face-up is a secondary signal).

This is the calibration surface for the recognizer. HD-Poker- and
resolution-specific by nature (CLAUDE.md §2) — expect to retune.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A region is a fractional box: (x, y, w, h), origin top-left, all in [0, 1].
Region = tuple[float, float, float, float]

# Six fixed screen seats, by position: top/bottom × left/center/right.
SEAT_KEYS = ("tl", "tc", "tr", "bl", "bc", "br")


def crop(frame, region: Region):
    """Crop a fractional region out of a BGR frame (numpy array)."""
    h, w = frame.shape[:2]
    x0 = max(0, int(round(region[0] * w)))
    y0 = max(0, int(round(region[1] * h)))
    x1 = min(w, int(round((region[0] + region[2]) * w)))
    y1 = min(h, int(round((region[1] + region[3]) * h)))
    return frame[y0:y1, x0:x1]


def split_row(region: Region, n: int, *, gap: float = 0.0) -> list[Region]:
    """Split a region horizontally into ``n`` equal sub-regions (with optional gap)."""
    x, y, w, h = region
    cell = (w - gap * (n - 1)) / n
    return [(x + i * (cell + gap), y, cell, h) for i in range(n)]


@dataclass(frozen=True)
class Seat:
    """The three things we read at a seat. All fractional regions."""

    key: str
    name: Region   # nameplate: username + stack text
    cards: Region  # the seat's two hole cards (face-up only for the hero)
    bet: Region    # chips wagered this street, in front of the seat


@dataclass
class TableLayout:
    name: str
    seats: dict[str, Seat] = field(default_factory=dict)
    board_strip: Region = (0.385, 0.495, 0.265, 0.105)
    pot: Region = (0.47, 0.55, 0.16, 0.045)
    button_search: Region = (0.30, 0.20, 0.45, 0.55)  # where the dealer 'D' disc roams
    n_board: int = 5

    def board_slots(self) -> list[Region]:
        return split_row(self.board_strip, self.n_board, gap=0.004)

    def flat_regions(self) -> dict[str, Region]:
        """All regions as a flat label->region dict (for overlay/cropping)."""
        out: dict[str, Region] = {"pot": self.pot}
        for i, slot in enumerate(self.board_slots(), start=1):
            out[f"board{i}"] = slot
        for s in self.seats.values():
            out[f"{s.key}_name"] = s.name
            out[f"{s.key}_cards"] = s.cards
            out[f"{s.key}_bet"] = s.bet
        return out


def _seat(key, name, cards, bet) -> Seat:
    return Seat(key=key, name=name, cards=cards, bet=bet)


# First-pass estimates from captures/table_ref_01.png (client ~1686x1172).
# name boxes are reasonably placed; cards/bet are rough and will be calibrated
# against a mid-hand frame (face-down card backs make seat card areas obvious).
DEFAULT_6MAX = TableLayout(
    name="hdpoker-6max",
    board_strip=(0.385, 0.495, 0.265, 0.105),
    pot=(0.47, 0.55, 0.16, 0.045),
    seats={
        "tl": _seat("tl", (0.16, 0.165, 0.16, 0.055), (0.17, 0.255, 0.13, 0.095), (0.24, 0.30, 0.10, 0.05)),
        "tc": _seat("tc", (0.52, 0.115, 0.16, 0.055), (0.44, 0.205, 0.13, 0.095), (0.46, 0.32, 0.10, 0.05)),
        "tr": _seat("tr", (0.72, 0.175, 0.16, 0.055), (0.70, 0.255, 0.13, 0.095), (0.64, 0.30, 0.10, 0.05)),
        "bl": _seat("bl", (0.165, 0.815, 0.16, 0.055), (0.18, 0.69, 0.13, 0.095), (0.27, 0.66, 0.10, 0.05)),
        "bc": _seat("bc", (0.44, 0.85, 0.16, 0.055), (0.45, 0.72, 0.13, 0.095), (0.46, 0.66, 0.10, 0.05)),
        "br": _seat("br", (0.68, 0.815, 0.16, 0.055), (0.69, 0.69, 0.13, 0.095), (0.62, 0.66, 0.10, 0.05)),
    },
)


def annotate(frame, layout: TableLayout):
    """Return a copy of ``frame`` with labeled region boxes drawn (BGR)."""
    import cv2  # lazy: only needed for the calibration overlay

    out = frame.copy()
    h, w = out.shape[:2]
    palette = {"name": (0, 255, 0), "cards": (255, 120, 0), "bet": (0, 200, 255), "board": (0, 200, 255), "pot": (200, 0, 255)}
    for label, region in layout.flat_regions().items():
        x0 = int(round(region[0] * w))
        y0 = int(round(region[1] * h))
        x1 = int(round((region[0] + region[2]) * w))
        y1 = int(round((region[1] + region[3]) * h))
        kind = label.split("_")[-1] if "_" in label else ("board" if label.startswith("board") else label)
        colour = palette.get(kind, (0, 255, 0))
        cv2.rectangle(out, (x0, y0), (x1, y1), colour, 2)
        cv2.putText(
            out, label, (x0 + 2, max(12, y0 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, colour, 1, cv2.LINE_AA,
        )
    return out
