# Hold'em Study Coach

A **post-hand** study tool for Texas Hold'em on the **HD Poker** social app
(play money). It reconstructs a finished hand into a structured record, computes
objective numbers (equity, pot odds, EV) at each hero decision, and turns those
numbers into plain-language coaching.

> **Guardrail:** this is post-hand only. No real-time assistance, no on-table
> overlay, play money only. See [`CLAUDE.md`](./CLAUDE.md) §1.

## Status — Milestone 1 (analysis + coaching)

The valuable, durable half is built and tested against synthetic hands:

- `holdem_coach/handhistory.py` — the `HandHistory` schema (the only seam).
- `holdem_coach/analysis/` — deterministic equity (Monte Carlo via `treys`),
  pot odds / required equity, simple EV, static 6-max RFI charts, and a
  decision-scorer that walks each hero decision and attaches numbers + deltas.
- `holdem_coach/coaching/` — coaching layer. **Mocked by default** (no network);
  pass an Anthropic client for real LLM coaching. The model explains only — it
  never produces a number.
- `holdem_coach/capture/` — empty placeholder for Milestone 2 (vision).

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows PowerShell
python -m pip install -U pip
pip install -e ".[dev]"                # runtime + pytest
```

(Optional extras: `.[coaching]` for the Anthropic SDK, `.[capture]` for the
future vision deps.)

## Run as an app (desktop panel)

A Tkinter review panel — open a hand (or pick a bundled sample) and read the
colour-coded review. Tkinter ships with Python, so there are no extra deps.

```powershell
python -m holdem_coach gui
```

Toggle **AI coaching** in the toolbar to use the real Anthropic backend instead
of the mock (needs `ANTHROPIC_API_KEY` set and the `[coaching]` extra installed;
see below). The window stays responsive during Monte Carlo / API calls — work
runs on a background thread.

### Standalone .exe (no Python needed)

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[build]"     # one time
powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1
```

Produces `dist\HoldemCoach\HoldemCoach.exe` — double-click to run, and the whole
`dist\HoldemCoach\` folder is shareable.

## Run from the command line

```powershell
python -m holdem_coach analyze sample_hands/hand1_preflop_mistake.json
python -m holdem_coach analyze sample_hands/hand2_pot_odds.json
python -m holdem_coach analyze sample_hands/hand3_clean_line.json
```

Equity is Monte Carlo; `--seed` makes it reproducible and `--iterations`
trades speed for precision. Add `--llm` for real Anthropic coaching.

## Test

```powershell
pytest
```

The math layer is unit-tested against known values (e.g. AA vs KK ≈ 81%).

## Default table format

6-max cash, 100bb (blinds 1/2, 200 starting stack) — matches the schema example
and sets the preflop charts. Adjust `holdem_coach/analysis/ranges.py` for other
formats.

## Layout

```
holdem_coach/
  handhistory.py        schema + JSON (de)serialization + validation
  analysis/             equity, odds, ranges, scorer  (no LLM, no capture import)
  coaching/             mock + Anthropic coaching backends
  capture/              placeholder (Milestone 2)
sample_hands/           3 hand-written hands
tests/                  pytest suite
```

## Real LLM coaching (optional)

```python
import anthropic
from holdem_coach.handhistory import HandHistory
from holdem_coach.analysis.scorer import score_hand
from holdem_coach.coaching.coach import coach_decisions

hh = HandHistory.load("sample_hands/hand1_preflop_mistake.json")
decisions = score_hand(hh)
notes = coach_decisions(decisions, client=anthropic.Anthropic())  # needs ANTHROPIC_API_KEY
```
