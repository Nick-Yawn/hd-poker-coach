"""Coaching layer implementation.

Two backends behind one interface:
  - ``coach_decisions(..., client=None)`` -> deterministic *mock* notes built
    only from the engine's numbers/deltas (no network). This is the default and
    keeps Milestone 1 unblocked.
  - pass an Anthropic ``client`` to get real LLM coaching. The system prompt
    forbids the model from inventing or recomputing any number — it teaches
    around the figures we hand it (CLAUDE.md §7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..analysis.scorer import DecisionAnalysis

MODEL = "claude-opus-4-8"

_SYSTEM_PROMPT = """You are a Texas Hold'em study coach reviewing a hand that is \
already over. You will receive structured decision data with PRE-COMPUTED \
numbers (equity, required equity, EV, pot, deltas).

Hard rules:
- You EXPLAIN and TEACH only. Never compute, estimate, or alter any number. \
Use the figures exactly as given.
- This is post-hand review. Never phrase anything as advice for a live/pending \
decision.
- For each decision return: a one-sentence WHY, a concept tag, and one concrete \
TAKEAWAY. Be concise and non-repetitive.
Respond as compact JSON: a list of objects with keys \
"explanation", "concept", "takeaway"."""


@dataclass
class CoachingNote:
    concept: str
    explanation: str
    takeaway: str

    def to_dict(self) -> dict:
        return {
            "concept": self.concept,
            "explanation": self.explanation,
            "takeaway": self.takeaway,
        }


# --------------------------------------------------------------------------- #
# Mock backend (default)
# --------------------------------------------------------------------------- #
_TAKEAWAYS = {
    "preflop range": "Open only hands inside your position's chart; fold the rest.",
    "pot odds": "Call only when your equity beats the price the pot is laying you.",
    "pot control / aggression": "With no bet to face, choose bet vs check by your "
    "plan for the next street, not by fear.",
}


def _mock_note(d: DecisionAnalysis) -> CoachingNote:
    """Build a note purely from engine output — invents no numbers."""
    lead = f"{d.street.capitalize()}: you chose to {d.hero_action}"
    if d.facing_bet:
        lead += (
            f", facing {d.to_call:g} into {d.pot_before:g} "
            f"(need {d.required_equity:.0%}, have ~{d.equity:.0%})"
        )
    explanation = lead + ". " + d.delta
    takeaway = _TAKEAWAYS.get(d.concept, f"Baseline line here: {d.baseline}.")
    return CoachingNote(concept=d.concept, explanation=explanation, takeaway=takeaway)


# --------------------------------------------------------------------------- #
# LLM backend (opt-in)
# --------------------------------------------------------------------------- #
def _decision_payload(d: DecisionAnalysis) -> dict:
    """Only the engine's facts — the model gets numbers, never makes them."""
    return {
        "street": d.street,
        "board": d.board,
        "hero_cards": d.hero_cards,
        "hero_class": d.hero_class,
        "action_taken": d.hero_action,
        "to_call": d.to_call,
        "pot_before": d.pot_before,
        "equity": None if d.equity is None else round(d.equity, 4),
        "required_equity": (
            None if d.required_equity is None else round(d.required_equity, 4)
        ),
        "ev_call": None if d.ev_call is None else round(d.ev_call, 4),
        "baseline": d.baseline,
        "delta": d.delta,
        "concept": d.concept,
        "is_leak": d.leak,
    }


def _llm_notes(decisions, client) -> list[CoachingNote]:
    payload = [_decision_payload(d) for d in decisions]
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": "Coach these decisions:\n" + json.dumps(payload, indent=2),
            }
        ],
    )
    text = "".join(
        block.text for block in msg.content if getattr(block, "type", None) == "text"
    )
    data = json.loads(text)
    return [
        CoachingNote(
            concept=item.get("concept", ""),
            explanation=item.get("explanation", ""),
            takeaway=item.get("takeaway", ""),
        )
        for item in data
    ]


def coach_decisions(
    decisions: list[DecisionAnalysis], *, client=None
) -> list[CoachingNote]:
    """Return one CoachingNote per decision.

    ``client=None`` (default) uses the deterministic mock. Pass an Anthropic
    client to use the real LLM. Either way, all numbers originate in the engine.
    """
    if client is None:
        return [_mock_note(d) for d in decisions]
    return _llm_notes(decisions, client)
