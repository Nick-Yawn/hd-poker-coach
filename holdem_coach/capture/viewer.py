"""Live recognizer view — a SEPARATE debug window (never an on-table overlay).

Mirrors the captured HD Poker frame into its own window and draws what the
vision layer detects: OCR token boxes, per-seat name/stack/action, the board
cards, stakes/pot. This is developer telemetry, NOT coaching:

  GUARDRAIL (CLAUDE.md §1): this window shows only *detections*, never analysis,
  numbers, hints, or advice, and it is a standalone window — it is never painted
  over the live HD Poker table. That boundary is the whole point.

It is also a great live test harness for the recognizer.
"""

from __future__ import annotations


def _draw_label(cv2, img, text, org, *, fg, bg=(0, 0, 0), scale=0.5, pad=3):
    (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    x, y = int(org[0]), int(org[1])
    cv2.rectangle(img, (x - pad, y - th - pad), (x + tw + pad, y + base + pad), bg, -1)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, fg, 1, cv2.LINE_AA)


def annotate_recognition(frame, tokens, state, board):
    """Draw detections on a copy of the frame and return it (BGR)."""
    import cv2

    vis = frame.copy()
    h, w = vis.shape[:2]

    # Faint boxes for every OCR token.
    for t in tokens:
        x0, y0 = int(t.left * w), int(t.top * h)
        x1, y1 = int(t.right * w), int(t.bottom * h)
        cv2.rectangle(vis, (x0, y0), (x1, y1), (90, 90, 90), 1)

    # Per-seat readout.
    for s in state.seats:
        x, y = int(s.cx * w), int(s.cy * h)
        fg = (0, 255, 0) if s.is_hero else (255, 255, 255)
        stack = f" {s.stack:g}" if s.stack is not None else ""
        act = f" [{s.action}]" if s.action else ""
        tag = "HERO " if s.is_hero else ""
        _draw_label(cv2, vis, f"{tag}{s.name or '?'}{stack}{act}", (x, y),
                    fg=fg, bg=(40, 40, 40))

    # Board cards (top-center).
    board_txt = "BOARD: " + (" ".join(board) if board else "-")
    _draw_label(cv2, vis, board_txt, (int(w * 0.34), int(h * 0.06)),
                fg=(0, 220, 255), bg=(20, 20, 20), scale=0.7)

    # Stakes / pot (top-left).
    stake = (f"{state.small_blind:g}/{state.big_blind:g}"
             if state.big_blind else "?")
    pot = f"  pot {state.pot:g}" if state.pot else ""
    _draw_label(cv2, vis, f"stakes {stake}{pot}", (12, int(h * 0.12)),
                fg=(200, 200, 200), bg=(20, 20, 20))

    # Boundary reminder, so this is never mistaken for an on-table aid.
    _draw_label(cv2, vis, "DEBUG VIEW - detections only, no advice",
                (12, h - 14), fg=(0, 215, 255), bg=(0, 0, 0), scale=0.6)
    return vis


def recognize(frame, *, hero_name=None):
    """Run the full per-frame recognition stack on one frame."""
    from .cards import read_board
    from .interpret import interpret
    from .ocr import read_tokens

    tokens = read_tokens(frame)
    state = interpret(tokens, hero_name=hero_name)
    board = read_board(frame)
    return tokens, state, board


def run_viewer(
    window_substr: str,
    *,
    hero_name: str | None = None,
    scale: float = 0.6,
    frames: int | None = None,
    show: bool = True,
    save_path: str | None = None,
) -> int:
    """Live loop: grab -> recognize -> draw in a separate window.

    ``frames`` limits the iterations (None = until 'q'/window closed). ``show``
    toggles the live window; ``save_path`` writes the last annotated frame
    (used for headless verification).
    """
    import cv2

    from .grabber import WindowGrabber

    title = "HD Poker recognizer (debug) - press Q to close"
    count = 0
    last = None
    with WindowGrabber(window_substr) as grabber:
        while frames is None or count < frames:
            frame = grabber.grab()
            tokens, state, board = recognize(frame, hero_name=hero_name)
            last = annotate_recognition(frame, tokens, state, board)
            count += 1
            if show:
                disp = cv2.resize(last, None, fx=scale, fy=scale,
                                  interpolation=cv2.INTER_AREA)
                cv2.imshow(title, disp)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                try:
                    if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                        break
                except cv2.error:
                    break
    if show:
        cv2.destroyAllWindows()
    if save_path is not None and last is not None:
        cv2.imwrite(save_path, last)
    return count
