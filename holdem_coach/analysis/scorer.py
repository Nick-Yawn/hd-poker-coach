"""Decision-scorer: walk each hero decision and attach numbers + deltas.

Replays the betting (treating ``Action.amount`` as chips added — see CLAUDE.md
§5) to reconstruct, at each hero decision point: the pot before the hero acts,
the amount to call, and which opponents are live. It then attaches:

  - equity (Monte Carlo vs an estimated villain range, CLAUDE.md §6)
  - required equity from pot odds (if facing a bet)
  - simple EV of calling (if facing a bet)
  - a baseline + delta (preflop = RFI chart; postflop = pot-odds sanity)

This layer is deterministic apart from seeded Monte Carlo. No LLM, no I/O.
The output objects feed the coaching layer, which supplies the English.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..handhistory import HandHistory, STREETS
from .equity import equity_vs_combos
from .odds import ev_call, required_equity
from .ranges import classify_hand, expand_range, opening_range


@dataclass
class DecisionAnalysis:
    """Everything the coaching layer needs about one hero decision."""

    street: str
    board: list[str]
    hero_cards: list[str]
    hero_class: str
    hero_action: str
    hero_amount: float
    to_call: float
    pot_before: float
    facing_bet: bool
    equity: float | None
    required_equity: float | None
    ev_call: float | None
    villain_desc: str
    baseline: str          # what the Milestone-1 baseline would do
    delta: str             # human-readable gap description
    tag: str               # short machine tag, e.g. "OK", "LEAK", "THIN", "INFO"
    concept: str           # concept label for the coaching layer
    leak: bool             # did the baseline flag a clear mistake?

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        return d


# --------------------------------------------------------------------------- #
# Betting replay
# --------------------------------------------------------------------------- #
@dataclass
class _State:
    pot: float = 0.0
    street: str = "preflop"
    committed: dict[int, float] = field(default_factory=dict)  # this street
    folded: set[int] = field(default_factory=set)
    last_aggressor: int | None = None  # seat that set the current bet this street

    @property
    def current_bet(self) -> float:
        return max(self.committed.values(), default=0.0)

    def reset_street(self, street: str) -> None:
        self.street = street
        self.committed = {}
        self.last_aggressor = None


def _estimate_villain(hh: HandHistory, st: _State, decision_street: str):
    """Pick a villain and an estimated combo range at a hero decision.

    Preference order, Milestone 1:
      - the last aggressor this street if there is one, else any live opponent;
      - if that villain *raised preflop*, use their position RFI range (carried
        forward to later streets, filtered by the board);
      - otherwise fall back to a random opponent (full remaining deck).
    Returns (description, combos).
    """
    live = [
        p.seat
        for p in hh.players
        if p.seat != hh.hero_seat and p.seat not in st.folded
    ]
    villain_seat = st.last_aggressor if st.last_aggressor in live else (
        live[0] if live else None
    )

    # Did this villain open-raise preflop? If so, use their RFI range.
    raised_preflop = any(
        a.seat == villain_seat and a.street == "preflop" and a.action == "raise"
        for a in hh.actions
    )
    if villain_seat is not None and raised_preflop:
        pos = hh.seat_position(villain_seat)
        rng = opening_range(pos)
        if rng:
            return (f"seat {villain_seat} ({pos}) RFI range", expand_range(rng))

    # Fallback: random opponent hand. We pass an empty combo list sentinel and
    # let the caller substitute a random-opponent equity call.
    desc = (
        f"seat {villain_seat} (random hand)"
        if villain_seat is not None
        else "random hand"
    )
    return desc, None


def _preflop_baseline(hh: HandHistory, action: str) -> tuple[str, str, str, str, bool]:
    """Compare a hero preflop action to the position RFI chart.

    Returns (baseline, delta, tag, concept, leak).
    """
    pos = hh.hero_position or "?"
    cls = classify_hand(*hh.hero_hole_cards)
    rng = opening_range(pos)
    in_range = cls in rng
    concept = "preflop range"

    if action in ("bet", "raise"):
        if in_range:
            return (
                f"open/raise {cls} from {pos}",
                f"{cls} is a standard {pos} open — in the chart.",
                "OK",
                concept,
                False,
            )
        return (
            f"fold {cls} from {pos}",
            f"{cls} is outside the {pos} opening range; this open is too loose.",
            "LEAK",
            concept,
            True,
        )
    if action == "call":
        # Cold-calling / flatting. Flag clearly trashy flats; otherwise neutral.
        if in_range:
            return (
                f"raise or call {cls} from {pos}",
                f"{cls} is a reasonable continue from {pos}.",
                "OK",
                concept,
                False,
            )
        return (
            f"fold {cls} from {pos}",
            f"{cls} is outside a standard {pos} range; flatting it bleeds chips.",
            "LEAK",
            concept,
            True,
        )
    # check / fold preflop — informational.
    return (
        f"{action} {cls} from {pos}",
        f"{action} with {cls} from {pos}.",
        "INFO",
        concept,
        False,
    )


def score_hand(
    hh: HandHistory,
    *,
    iterations: int = 4000,
    seed: int | None = 1234,
) -> list[DecisionAnalysis]:
    """Walk the betting and return a DecisionAnalysis per hero decision."""
    from .equity import equity_vs_random  # local import avoids cycle at import

    hh.validate()
    st = _State()
    results: list[DecisionAnalysis] = []
    hero = hh.hero_seat
    hero_cards = hh.hero_hole_cards
    hero_class = classify_hand(*hero_cards)
    current_street = None

    for a in hh.actions:
        if a.street != current_street:
            st.reset_street(a.street)
            current_street = a.street

        is_hero = a.seat == hero and a.action not in ("post",)
        if is_hero:
            to_call = max(0.0, st.current_bet - st.committed.get(hero, 0.0))
            pot_before = st.pot
            # Pot-odds / EV framing only applies to a pure price decision: the
            # hero is paying `to_call` to continue (call or fold). When the hero
            # bets or raises they are setting the price, not taking it, so the
            # "required equity to call" number would mislead.
            facing_bet = to_call > 1e-9 and a.action in ("call", "fold")
            board = hh.board.cards_through(a.street)

            # --- equity vs estimated villain range ---
            desc, combos = _estimate_villain(hh, st, a.street)
            try:
                if combos is None:
                    equity = equity_vs_random(
                        hero_cards, board, iterations=iterations, seed=seed
                    )
                else:
                    equity = equity_vs_combos(
                        hero_cards, board, combos,
                        iterations=iterations, seed=seed,
                    )
            except ValueError:
                equity = equity_vs_random(
                    hero_cards, board, iterations=iterations, seed=seed
                )

            req = required_equity(to_call, pot_before) if facing_bet else None
            ev = ev_call(equity, pot_before, to_call) if facing_bet else None

            # --- baseline + delta ---
            if a.street == "preflop":
                baseline, delta, tag, concept, leak = _preflop_baseline(hh, a.action)
            else:
                baseline, delta, tag, concept, leak = _postflop_baseline(
                    a.action, equity, req, ev
                )

            results.append(
                DecisionAnalysis(
                    street=a.street,
                    board=board,
                    hero_cards=hero_cards,
                    hero_class=hero_class,
                    hero_action=a.action,
                    hero_amount=a.amount,
                    to_call=to_call,
                    pot_before=pot_before,
                    facing_bet=facing_bet,
                    equity=equity,
                    required_equity=req,
                    ev_call=ev,
                    villain_desc=desc,
                    baseline=baseline,
                    delta=delta,
                    tag=tag,
                    concept=concept,
                    leak=leak,
                )
            )

        # --- apply the action to the running state ---
        _apply(st, a)

    return results


def _postflop_baseline(action, equity, req, ev) -> tuple[str, str, str, str, bool]:
    """Pot-odds sanity check for a postflop decision."""
    if req is None:  # not facing a bet
        concept = "pot control / aggression"
        return (
            f"{action} (no bet faced)",
            f"No price to pay; ~{equity:.0%} equity to realize.",
            "INFO",
            concept,
            False,
        )

    concept = "pot odds"
    margin = 0.03  # tolerance band around the break-even price
    if action == "call":
        if equity + margin < req:
            return (
                "fold",
                f"call needs {req:.0%} equity but you hold ~{equity:.0%} — a losing call.",
                "LEAK",
                concept,
                True,
            )
        if equity > req:
            return (
                "call",
                f"~{equity:.0%} equity beats the {req:.0%} you need — a profitable call.",
                "OK",
                concept,
                False,
            )
        return (
            "call (thin)",
            f"~{equity:.0%} equity vs {req:.0%} needed — close, roughly break-even.",
            "THIN",
            concept,
            False,
        )
    if action == "fold":
        if equity > req + margin:
            return (
                "call",
                f"you had ~{equity:.0%} vs {req:.0%} needed — folding here is too tight.",
                "LEAK",
                concept,
                True,
            )
        return (
            "fold",
            f"~{equity:.0%} equity vs {req:.0%} needed — folding is fine.",
            "OK",
            concept,
            False,
        )
    # bet / raise / check while a bet is somehow faced — informational.
    return (
        action,
        f"{action} with ~{equity:.0%} equity.",
        "INFO",
        concept,
        False,
    )


def _apply(st: _State, a) -> None:
    """Mutate state for one action. ``amount`` = chips added this action."""
    if a.action == "fold":
        st.folded.add(a.seat)
        return
    if a.action in ("check",):
        return
    if a.action in ("post", "call", "bet", "raise"):
        st.committed[a.seat] = st.committed.get(a.seat, 0.0) + a.amount
        st.pot += a.amount
        if a.action in ("bet", "raise"):
            st.last_aggressor = a.seat
        return
