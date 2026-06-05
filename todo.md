# TODO / Roadmap

A simple running list. Post-hand Hold'em study coach for HD Poker.

## Now (action reconstruction — the open problem)
- [ ] **Dealer-button glyph** detection → which nameplate is the button →
      positions by clockwise rotation around the table centroid (drop blind
      dependence)
- [ ] **Record real hands** with known action sequences → end-to-end test
      fixtures (anonymize player names; the buffered pipeline is the recorder)
- [ ] **Action reconstructor**: bet-pill deltas + active-player highlight +
      stack deltas → ordered per-street actions, built against the recorded suite
- [ ] Result fidelity: winner→seat mapping + hero_net (currently approximate)

## Soon (capture polish)
- [ ] Bet reading: catch central/raise pills (beyond the seat radius)
- [ ] Suit accuracy: validate across more decks/table themes
- [ ] Per-table region drift (board/cards shift slightly by theme) — snap vs fixed

## Done
- [x] **M1**: HandHistory schema + equity/EV/pot-odds engine + decision scorer +
      coaching (mock + Anthropic), CLI + GUI + .exe — all tested
- [x] Capture: frame grab, OCR-first interpret → TableState, card reader
      (board + hero hole cards, any seat), temporal tracker → HandHistory
- [x] Live recognizer overlay (on-table, detections-only, excluded from capture)
- [x] GPU OCR (DirectML, ~2.5×) + frame-skip
- [x] Live `track` loop → post-hand review per hand
- [x] Buffered producer-consumer pipeline (don't drop fast actions)
- [x] PRE-FLOP tag as hand-start signal (deferred position anchoring)

## Later / ideas
- [ ] Wire real LLM coaching into the live `track` output (`--llm` exists)
- [ ] Session view (review many hands; leak trends over time)
- [ ] Rebuild the `.exe` with the full capture pipeline

## Guardrails (do not break)
- Post-hand only — no output surfaced during a live decision (no RTA)
- On-table overlay shows DETECTIONS only, never computed results/coaching
- Play money only (HD Poker)
