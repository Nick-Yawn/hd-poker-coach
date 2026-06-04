"""Tests for the deterministic OCR-token interpreter.

Self-contained: the synthetic token list mirrors a real HD Poker frame
(captures are gitignored, so we encode the layout here).
"""

import pytest

from holdem_coach.capture.interpret import (
    action_of,
    interpret,
    name_similarity,
    parse_amount,
    parse_blinds,
)
from holdem_coach.capture.ocr import Token


@pytest.mark.parametrize(
    "text,expected",
    [
        ("500", 500.0),
        ("250", 250.0),
        ("47K", 47_000.0),
        ("52.85K", 52_850.0),
        ("183.7K", 183_700.0),
        ("1,115", 1115.0),
        ("$2,500", 2500.0),
        ("3.2M", 3_200_000.0),
        ("630,211,864", 630_211_864.0),
    ],
)
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text", ["", "FOLD", "abc", "250/500", "12:30 PM"])
def test_parse_amount_rejects_non_amounts(text):
    assert parse_amount(text) is None


def test_parse_blinds():
    assert parse_blinds("250/500") == (250.0, 500.0)
    assert parse_blinds("1K/2K") == (1000.0, 2000.0)
    assert parse_blinds("nope") is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("FOLD", "fold"), ("Folded", "fold"), ("CHECK", "check"),
        ("CALL", "call"), ("RAISE", "raise"), ("ALL IN", "allin"),
        ("BET", "bet"), ("hello", None),
    ],
)
def test_action_of(text, expected):
    assert action_of(text) == expected


def test_name_similarity_properties():
    # Exact (case/punctuation-insensitive) match is 1.0 — this is the case that
    # matters for hero detection, and digit-bearing names OCR cleanly.
    assert name_similarity("ColdMuck71", "coldmuck71") == 1.0
    # An OCR slip still scores far higher against the true name than a stranger.
    assert name_similarity("cerogtihdi", "corgtholi") > name_similarity(
        "cerogtihdi", "SlowBet25"
    )
    assert name_similarity("vac7467", "SlowBet25") < 0.5


def _tok(text, cx, cy, score=0.99):
    return Token(text=text, score=score, cx=cx, cy=cy, w=0.05, h=0.02)


def _real_frame_tokens():
    # Mirrors captures/hand_01.png (a 9-max table, 7 seated, hero folded).
    return [
        _tok("ColdMuck71", 0.89, 0.01),       # account name in the top bar
        _tok("250/500", 0.10, 0.09),          # stakes
        _tok("cacapucine", 0.40, 0.23), _tok("50K", 0.40, 0.25),
        _tok("dstaats", 0.60, 0.23), _tok("49.5K", 0.60, 0.25),
        _tok("vac7467", 0.30, 0.27), _tok("50K", 0.30, 0.29),
        _tok("cerogtihdi", 0.70, 0.27), _tok("183.7K", 0.71, 0.29),
        _tok("ColdMuck71", 0.32, 0.78), _tok("47K", 0.32, 0.79),
        _tok("FOLD", 0.32, 0.82),
        _tok("maxfreddie", 0.68, 0.78), _tok("52.85K", 0.68, 0.79),
        _tok("SlowBet25", 0.50, 0.80), _tok("160.5K", 0.50, 0.82),
        _tok("500", 0.60, 0.48),              # a bet in the middle (no name above)
        _tok("2:19 PM cacapucine went all in with 50K!", 0.07, 0.92),
    ]


def test_interpret_reads_stakes():
    st = interpret(_real_frame_tokens(), hero_name="ColdMuck71")
    assert (st.small_blind, st.big_blind) == (250.0, 500.0)


def test_interpret_finds_all_seated_players():
    st = interpret(_real_frame_tokens(), hero_name="ColdMuck71")
    names = {s.name for s in st.seats}
    assert names == {
        "cacapucine", "dstaats", "vac7467", "cerogtihdi",
        "ColdMuck71", "maxfreddie", "SlowBet25",
    }


def test_interpret_reads_exact_stacks():
    st = interpret(_real_frame_tokens(), hero_name="ColdMuck71")
    by_name = {s.name: s.stack for s in st.seats}
    assert by_name["cerogtihdi"] == 183_700.0
    assert by_name["ColdMuck71"] == 47_000.0
    assert by_name["maxfreddie"] == 52_850.0


def test_interpret_identifies_hero_and_action():
    st = interpret(_real_frame_tokens(), hero_name="ColdMuck71")
    hero = st.hero
    assert hero is not None
    assert hero.name == "ColdMuck71"
    assert hero.action == "fold"


def test_interpret_does_not_treat_center_bet_as_a_seat():
    # The lone '500' in the middle has no name above it -> not a seat.
    st = interpret(_real_frame_tokens(), hero_name="ColdMuck71")
    assert len(st.seats) == 7


def test_interpret_collects_chat():
    st = interpret(_real_frame_tokens(), hero_name="ColdMuck71")
    assert any("went all in" in line for line in st.chat)


def test_interpret_without_hero_name_marks_no_hero():
    st = interpret(_real_frame_tokens())
    assert st.hero is None
    assert len(st.seats) == 7


def test_interpret_assigns_bets_to_nearest_seat():
    # A bet pill just toward the centre from a seat is claimed by that seat.
    tokens = [
        _tok("250/500", 0.10, 0.09),
        _tok("SlowBet25", 0.50, 0.80), _tok("160.5K", 0.50, 0.82),
        _tok("maxfreddie", 0.68, 0.78), _tok("52.85K", 0.68, 0.79),
        _tok("500", 0.50, 0.68),   # SlowBet25's blind, just above the seat
        _tok("250", 0.66, 0.69),   # maxfreddie's blind
    ]
    st = interpret(tokens, hero_name="SlowBet25")
    bets = {s.name: s.bet for s in st.seats}
    assert bets["SlowBet25"] == 500.0
    assert bets["maxfreddie"] == 250.0


def test_interpret_stack_not_misread_as_bet():
    # The stack below a name must not also be claimed as a bet.
    tokens = [
        _tok("SlowBet25", 0.50, 0.80), _tok("160.5K", 0.50, 0.82),
    ]
    st = interpret(tokens, hero_name="SlowBet25")
    assert st.seats[0].stack == 160_500.0
    assert st.seats[0].bet is None
