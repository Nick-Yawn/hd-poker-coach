# CLAUDE.md — Hold'em Study Coach

> Drop this file in the project root. Claude Code reads `CLAUDE.md` automatically
> as standing context every session. Read it fully before writing any code.

---

## 1. What this is (and what it is NOT)

A **post-hand poker study tool** for **Texas Hold'em** on the **HD Poker social
app (play money)**. It watches hands as they happen, and **once a hand is
completely over**, it reconstructs the hand and gives the player objective
calculations plus plain-language coaching so they can learn faster.

**Hard guardrails — do not violate these, ever:**

- **No real-time assistance (RTA).** RTA = influencing a *pending* decision. We
  never do that. Capture may run continuously (you can't reconstruct a betting
  sequence from the final frame alone), but **no analysis, hint, number, or
  output is ever surfaced to the user while a decision is live.** Output is
  released only after the hand is fully resolved.
- **No on-table overlay.** Results appear in a separate panel / terminal output,
  never painted over the live table. This reinforces the boundary technically
  and in spirit.
- **Play money only.** Scope is the HD Poker social app. No real-money sites.
- If a feature request would blur the post-hand boundary, flag it and stop.
  Ask the human before proceeding.

---

## 2. Architecture (the core reframe)

The valuable, durable artifact is a **hand reconstructor**. Everything
downstream operates on a structured `HandHistory` record — **text, not pixels**.

```
[ capture layer ]      observes the live table, emits state transitions
       │                (THROWAWAY-AND-REWRITE per UI layout / resolution)
       ▼
[ HandHistory record ] structured: positions, hole cards, board, full betting seq
       │                (THE DURABLE INTERFACE — everything below depends only on this)
       ▼
[ analysis engine ]    deterministic: equity, pot odds, EV at each hero decision
       │
       ▼
[ coaching layer ]     LLM: turns the numbers + deltas into teaching, in English
```

**Why this split matters:** the capture layer is fragile and HD-Poker-specific;
the analysis + coaching layers are durable and testable. Keep them in **separate
packages** so the vision half can be rewritten without touching the valuable
half. The analysis engine must never import anything from the capture layer.

---

## 3. Build order — DE-RISK VALUE FIRST

Do NOT start with the computer-vision capture layer. Build and validate the
analysis + coaching loop against hand-typed / synthetic hands first. If the
coaching turns out mediocre, we've saved ourselves the entire vision slog.

- **Milestone 1 (DO THIS FIRST): Analysis + coaching on synthetic hands.**
  `HandHistory` schema, the equity/EV/pot-odds engine, a decision-scorer that
  walks each hero decision, and a coaching layer — all driven by hands typed by
  hand or generated. Prove "given a hand, here's useful feedback" works.
- **Milestone 2: Vision capture as an input adapter for HD Poker.** Only after
  M1 produces genuinely useful coaching. Emits the same `HandHistory` schema.
- **Milestone 3: Glue + session loop.** Detect hand end → reconstruct → analyze
  → coach → print review. CLI-first.

---

## 4. Tech stack

- **Language:** Python 3.12+. Use a venv (`python -m venv .venv`).
- **Hand evaluation / equity:** `treys` or `eval7` (fast 7-card eval + Monte
  Carlo). `pokerkit` is an option for full game-state logic if useful.
- **Ranges / GTO:** Milestone 1 uses static position-based preflop opening-range
  charts (UTG/MP/CO/BTN/SB/BB). Solver integration (`TexasSolver`,
  `postflop-solver`) is a *later* enhancement, not a Milestone 1 dependency.
- **Vision (Milestone 2 only):** `mss` (fast window capture), `opencv-python`
  (template matching), digit templates or constrained `pytesseract` for numbers.
- **Coaching:** Anthropic API. Structured decision data in → coaching text out.
- **Tests:** `pytest`. The math layer must be unit-tested against known values.

---

## 5. `HandHistory` schema

Implement as dataclasses with JSON (de)serialization. Target shape:

```json
{
  "hand_id": "synthetic-001",
  "table": { "max_seats": 6, "small_blind": 1, "big_blind": 2 },
  "hero_seat": 3,
  "button_seat": 1,
  "players": [
    { "seat": 1, "position": "BTN", "starting_stack": 200 },
    { "seat": 2, "position": "SB",  "starting_stack": 200 },
    { "seat": 3, "position": "BB",  "starting_stack": 200 }
  ],
  "hero_hole_cards": ["Ah", "Kd"],
  "board": { "flop": ["7c", "2d", "Ts"], "turn": "Qh", "river": "3s" },
  "actions": [
    { "street": "preflop", "seat": 1, "action": "raise", "amount": 6 },
    { "street": "preflop", "seat": 3, "action": "call",  "amount": 4 },
    { "street": "flop",    "seat": 3, "action": "check" }
  ],
  "result": { "winning_seats": [1], "pot": 12, "hero_net": -6 }
}
```

Card notation: rank in `23456789TJQKA`, suit in `cdhs` (e.g. `"Ah"`). Keep the
schema strict and validated — it's the contract both halves of the app depend on.

> **Action amount convention (this implementation):** `amount` is the number of
> chips the player *adds to the pot with this action* (the increment), not the
> "raise-to" total. Example from the schema above: BTN raises adding 6 (total
> bet level becomes 6); BB has the 2 blind already in, so the call adds 4. Checks
> and folds carry `amount` 0 (or omit it). This keeps `raise` and `call` amounts
> on the same footing and makes pot reconstruction a simple running sum.

---

## 6. Analysis engine — what to compute per HERO decision point

For each point where the hero had to act, compute and attach:

- **Equity:** hero's hole cards vs an estimated opponent range (Milestone 1 may
  start with equity vs a random hand, then improve to vs a position-based range)
  over the remaining board run-outs. Use Monte Carlo via the eval library.
- **Pot odds → required equity:** to call `C` into a pot of `P` (P already
  including the bet faced), required equity = `C / (P + C)`.
- **Simple EV:** EV(call) ≈ `equity * pot_won − (1 − equity) * amount_risked`
  for tractable single-decision spots. Multi-street EV needs a solver — defer.
- **Baseline comparison:** compare the hero's actual action to a baseline
  (Milestone 1 = preflop range chart for preflop; flag obviously dominated
  postflop calls/folds vs pot odds). Emit a **delta** describing the gap.

Keep all math in **pure, testable functions**. No LLM in this layer.

---

## 7. Coaching layer — contract

- **Input:** the structured decision points + computed numbers + deltas from §6.
- **Output:** for each notable decision, a concise English explanation of *why*,
  a concept tag (e.g. "pot odds", "range disadvantage", "position"), and one
  concrete takeaway. Keep it short and non-repetitive.
- **Rule:** the LLM **explains and teaches only**. It must not be the source of
  any number — all quantities come from the engine in §6. Never let the model
  recompute equity/EV itself.
- Mock this call first (return canned text) so Milestone 1 doesn't block on API
  wiring; swap in the real Anthropic call once the pipeline runs end to end.

---

## 8. First-session task list (ordered)

1. Scaffold project: package layout (`holdem_coach/analysis`, `holdem_coach/coaching`, `holdem_coach/capture` placeholder), venv, `pyproject.toml`, deps (`treys` or `eval7`, `pytest`).
2. Implement `HandHistory` dataclasses + JSON load/save + validation.
3. Hand-write **3 sample hands** in `sample_hands/` covering: a clear preflop
   mistake, a pot-odds call/fold spot, and a clean standard line.
4. Implement the equity / pot-odds / EV functions (§6) with unit tests against
   known equities (e.g. AA vs KK preflop ≈ 81%).
5. Implement the decision-scorer that walks hero decisions and attaches numbers + deltas.
6. Stub the coaching layer (§7) with mocked output; wire the full pipeline.
7. CLI entry point: `python -m holdem_coach analyze sample_hands/hand1.json`
   prints a readable post-hand review.
8. Only after the above feels useful: begin Milestone 2 (vision). Not before.

---

## 9. Conventions

- `analysis/` must not import from `capture/`. The schema is the only seam.
- Pure functions for math; side effects (I/O, API calls) at the edges.
- Commit per working increment (`git init` first) so experiments are reversible.

## 10. Open questions for the human (ask before assuming)

- Confirm HD Poker exposes no usable hand-history export (likely none — that's
  why the vision layer exists). If one *does* exist, prefer parsing it over
  vision entirely.
- Table format: cash vs tournament, 6-max vs 9-max, default starting stacks?
  These set the preflop range charts and EV assumptions.

> **Resolved (this build):** Default table format is **6-max cash, 100bb**
> (blinds 1/2, 200 starting stack) — matches the schema example. HD Poker
> hand-history export: assumed **none**; vision layer (M2) remains the input path.
