"""Deterministic interpreter: OCR tokens -> TableState.

This is the testable heart of the capture layer (the analogue of the math
engine). It takes the messy list of OCR tokens and applies pure rules — amount
parsing, action keywords, spatial seat clustering, fuzzy hero matching — to
produce a structured TableState. No pixels, no OCR, no randomness, so it can be
unit-tested by feeding synthetic token lists.

Seat clustering is anchored on STACK amounts (every seated player shows one), so
it is seat-count-agnostic: 6/8/9-max all work without hardcoded positions.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .ocr import Token
from .tablestate import SeatState, TableState

# --------------------------------------------------------------------------- #
# Token parsing
# --------------------------------------------------------------------------- #
_AMOUNT_RE = re.compile(r"^\$?(\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d+))?\s*([KMB])?$", re.I)
_BLINDS_RE = re.compile(r"^(\d[\d,]*(?:\.\d+)?[KMB]?)\s*/\s*(\d[\d,]*(?:\.\d+)?[KMB]?)$", re.I)
_CHAT_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:AM|PM)?\b", re.I)
_MULT = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}

# Max distance (frame fractions) from a seat to claim a bet pill as that seat's.
_BET_RADIUS = 0.18

# Action labels HD Poker paints under players, normalized.
_ACTIONS = {
    "FOLD": "fold", "FOLDED": "fold",
    "CHECK": "check", "CHECKED": "check",
    "CALL": "call", "CALLED": "call", "CALLS": "call",
    "BET": "bet", "BETS": "bet",
    "RAISE": "raise", "RAISED": "raise", "RAISES": "raise",
    "ALL IN": "allin", "ALLIN": "allin", "ALL-IN": "allin",
}

# UI chrome that is never a player name.
_STOPWORDS = {
    "HOME", "LOBBY", "PLAY", "STORE", "FREE BONUS", "HD POKER", "HDPOKER",
    "MAIN POT", "MAINPOT", "POT", "SIDE POT", "SIDEPOT", "HIT ENTER TO CHAT",
    "HITENTERTOCHAT", "SHOW", "MUCK", "WAITING", "SITTING OUT", "SIT OUT",
    # street / action-button labels that OCR can otherwise read as a name
    "PREFLOP", "FLOP", "TURN", "RIVER", "ALL IN", "ALLIN", "RAISE TO",
    "RAISETO", "ANY", "CALL ANY", "BET", "WIN", "WINNER",
}


def parse_amount(text: str) -> float | None:
    """Parse a chip amount like '183.7K', '52.85K', '1,115', '500' -> float."""
    if text is None:
        return None
    m = _AMOUNT_RE.match(text.strip())
    if not m:
        return None
    whole = m.group(1).replace(",", "")
    frac = m.group(2) or ""
    suffix = (m.group(3) or "").upper()
    num = float(f"{whole}.{frac}") if frac else float(whole)
    return num * _MULT[suffix]


def parse_blinds(text: str) -> tuple[float, float] | None:
    """Parse a stakes string like '250/500' -> (small_blind, big_blind)."""
    m = _BLINDS_RE.match(text.strip())
    if not m:
        return None
    sb, bb = parse_amount(m.group(1)), parse_amount(m.group(2))
    if sb is None or bb is None:
        return None
    return sb, bb


def action_of(text: str) -> str | None:
    return _ACTIONS.get(text.strip().upper())


def is_chat(token: Token) -> bool:
    """Chat-log lines carry a timestamp, or sit in the bottom-LEFT feed.

    The bottom-RIGHT holds the hero's action buttons (FOLD/CHECK/RAISE TO/bet
    sizes); restricting the non-timestamped fallback to the left half keeps those
    out of the chat stream.
    """
    return bool(_CHAT_RE.search(token.text)) or (token.cy > 0.88 and token.cx < 0.5)


def _normalize_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize_name(a), _normalize_name(b)).ratio()


# --------------------------------------------------------------------------- #
# Interpretation
# --------------------------------------------------------------------------- #
def _looks_like_name(token: Token) -> bool:
    t = token.text.strip()
    if len(t) < 3 or t.upper() in _STOPWORDS:
        return False
    if parse_amount(t) is not None or parse_blinds(t) is not None:
        return False
    if action_of(t) is not None:
        return False
    # Must contain at least two letters (usernames are wordy; pure symbols out).
    return sum(c.isalpha() for c in t) >= 2


def interpret(
    tokens: list[Token],
    *,
    hero_name: str | None = None,
    hero_match_threshold: float = 0.6,
) -> TableState:
    """Turn OCR tokens into a structured TableState (pure, deterministic)."""
    state = TableState(hero_name=hero_name)

    chat = [t for t in tokens if is_chat(t)]
    body = [t for t in tokens if t not in chat]
    state.chat = [t.text for t in sorted(chat, key=lambda t: t.cy)]

    # Stakes: a 'sb/bb' token, usually top-left.
    for t in body:
        blinds = parse_blinds(t.text)
        if blinds:
            state.small_blind, state.big_blind = blinds
            break

    # Pot: an amount adjacent to a 'MAIN POT'/'POT' label, else skip.
    pot_tok = None
    pot_label = next(
        (t for t in body
         if t.text.strip().upper() in ("MAIN POT", "MAINPOT", "POT")), None
    )
    if pot_label is not None:
        amounts = [
            (abs(t.cx - pot_label.cx) + abs(t.cy - pot_label.cy), t)
            for t in body
            if parse_amount(t.text) is not None
        ]
        near = [a for a in amounts if a[0] < 0.12]
        if near:
            pot_tok = min(near)[1]
            state.pot = parse_amount(pot_tok.text)

    # Seats: anchor on a name token with a stack amount just below it.
    names = [t for t in body if _looks_like_name(t)]
    amount_tokens = [t for t in body if parse_amount(t.text) is not None]
    used_amounts: set[int] = set()
    seats: list[SeatState] = []

    for name_tok in names:
        # Skip the top status bar (account name, etc.).
        if name_tok.cy < 0.12 or name_tok.cy > 0.9:
            continue
        stack_tok = _nearest_below(name_tok, amount_tokens, used_amounts)
        if stack_tok is None:
            continue
        used_amounts.add(id(stack_tok))
        action_tok = _nearest_below(
            name_tok,
            [t for t in body if action_of(t.text)],
            set(),
            max_dy=0.10,
        )
        seats.append(
            SeatState(
                name=name_tok.text,
                stack=parse_amount(stack_tok.text),
                action=action_of(action_tok.text) if action_tok else None,
                cx=name_tok.cx,
                cy=name_tok.cy,
            )
        )

    # Bets: leftover amounts in the play area, matched to the nearest seat
    # (chips wagered sit between a player and the pot, toward the centre).
    claimed = set(used_amounts)
    if pot_tok is not None:
        claimed.add(id(pot_tok))
    # A real wager is at least about a small blind; anything tinier (a stray '2'
    # or '6' OCR'd off a chip graphic) is noise, not a bet.
    bet_floor = max(1.0, (state.small_blind or 0.0) * 0.5)
    bet_candidates = [
        t for t in amount_tokens
        if id(t) not in claimed and 0.18 < t.cy < 0.82
        and (parse_amount(t.text) or 0.0) >= bet_floor
    ]
    pairs = []
    for si, seat in enumerate(seats):
        for t in bet_candidates:
            dx, dy = t.cx - seat.cx, t.cy - seat.cy
            d2 = dx * dx + dy * dy
            if d2 < _BET_RADIUS * _BET_RADIUS:
                pairs.append((d2, si, t))
    pairs.sort(key=lambda p: p[0])
    seat_done: set[int] = set()
    bet_done: set[int] = set()
    for d2, si, t in pairs:
        if si in seat_done or id(t) in bet_done:
            continue
        seats[si].bet = parse_amount(t.text)
        seat_done.add(si)
        bet_done.add(id(t))

    # Hero: the seat whose name best matches the configured hero name.
    if hero_name and seats:
        best = max(seats, key=lambda s: name_similarity(s.name or "", hero_name))
        if name_similarity(best.name or "", hero_name) >= hero_match_threshold:
            best.is_hero = True

    state.seats = seats
    return state


def _nearest_below(anchor: Token, candidates, used: set[int], *, max_dy: float = 0.05):
    """Closest candidate token sitting just below `anchor` (same column-ish)."""
    best = None
    best_d = 1e9
    for t in candidates:
        if id(t) in used:
            continue
        dy = t.cy - anchor.cy
        if dy <= 0 or dy > max_dy:
            continue
        dx = abs(t.cx - anchor.cx)
        if dx > 0.06:
            continue
        d = dy + dx
        if d < best_d:
            best, best_d = t, d
    return best
