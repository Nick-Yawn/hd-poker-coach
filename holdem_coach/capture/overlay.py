"""On-table transparent overlay of recognizer DETECTIONS (Windows).

A click-through, always-on-top, borderless window pinned over HD Poker's client
area. It draws what the vision layer *detects* — OCR token boxes, recognized
seat name/stack/action, board cards, stakes/pot — aligned to the live table, and
tracks the window if it moves or resizes.

BOUNDARY (CLAUDE.md §1, as scoped with the owner): this overlay shows ONLY
detections — facts already visible on the table, echoed back. It must NEVER
paint anything we *computed* to inform a decision: no equity, EV, ranges,
positions, baselines, or coaching. Those are "results" and stay in the post-hand
panel. Keep this window detection-only; that is what keeps it on the right side
of the no-real-time-assistance rule.

Recognition runs on a worker thread (it is ~1-2s/frame), so the overlay can
track window movement smoothly while detections refresh in the background.
Click-through (WS_EX_TRANSPARENT) means mouse input passes to the game, so you
can still play. Close it with Ctrl+C in the launching terminal (or --seconds).
"""

from __future__ import annotations

import threading
import time

# Sentinel background colour made fully transparent via Tk's -transparentcolor.
_TRANSPARENT = "#010203"


class Overlay:
    def __init__(self, window_substr: str, *, hero_name: str | None = None,
                 refresh: float = 0.2):
        if __import__("sys").platform != "win32":
            raise RuntimeError("the on-table overlay is Windows-only")
        from .window import ensure_dpi_aware

        ensure_dpi_aware()
        self.window_substr = window_substr
        self.hero_name = hero_name
        self.refresh = refresh
        self._latest = None
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # -- worker: grab + recognize, publish latest --------------------------- #
    def _worker(self) -> None:
        from .grabber import WindowGrabber
        from .viewer import recognize

        try:
            with WindowGrabber(self.window_substr) as grabber:
                while not self._stop.is_set():
                    try:
                        result = recognize(grabber.grab(), hero_name=self.hero_name)
                    except Exception:
                        result = None
                    with self._lock:
                        self._latest = result
                    self._stop.wait(self.refresh)
        except Exception:
            self._stop.set()

    # -- click-through, tool-window extended styles ------------------------- #
    @staticmethod
    def _make_clickthrough(root) -> None:
        import ctypes

        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x20
        WS_EX_TOOLWINDOW = 0x80  # keep it out of the taskbar/alt-tab
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
        )

    def run(self, *, seconds: float | None = None) -> int:
        import tkinter as tk

        from .window import client_box, find_windows

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.config(bg=_TRANSPARENT)
        root.attributes("-transparentcolor", _TRANSPARENT)
        try:
            root.tk.call("tk", "scaling", 1.0)
        except tk.TclError:
            pass
        canvas = tk.Canvas(root, bg=_TRANSPARENT, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        root.update_idletasks()
        self._make_clickthrough(root)

        worker = threading.Thread(target=self._worker, daemon=True)
        worker.start()

        ticks = 0
        start = None
        try:
            while not self._stop.is_set():
                wins = find_windows(self.window_substr)
                if wins:
                    box = client_box(wins[0])
                    root.geometry(
                        f"{box['width']}x{box['height']}+{box['left']}+{box['top']}"
                    )
                    self._draw(canvas, box["width"], box["height"])
                else:
                    canvas.delete("all")
                root.update_idletasks()
                root.update()
                ticks += 1
                # Use a wall clock derived from ticks (Date.now is fine here; this
                # is a live tool, not a resumable workflow).
                if seconds is not None:
                    start = start or time.perf_counter()
                    if time.perf_counter() - start >= seconds:
                        break
                time.sleep(0.03)
        except (KeyboardInterrupt, tk.TclError):
            pass
        finally:
            self._stop.set()
            try:
                root.destroy()
            except Exception:
                pass
        return ticks

    # -- draw the latest detections ----------------------------------------- #
    def _draw(self, canvas, W: int, H: int) -> None:
        with self._lock:
            result = self._latest
        canvas.delete("all")
        if not result:
            canvas.create_text(
                10, H - 12, anchor="w", fill="#fc0",
                text="recognizer starting…", font=("Consolas", 10),
            )
            return
        tokens, state, board_located = result

        for t in tokens:
            canvas.create_rectangle(
                t.left * W, t.top * H, t.right * W, t.bottom * H,
                outline="#55aaff", width=1,
            )

        # Recognized cards: boxed + labeled in place (this is the "recognition
        # on the cards" — rank from OCR, suit from colour + pip shape).
        for card, (fx, fy, fw, fh) in board_located:
            canvas.create_rectangle(
                fx * W, fy * H, (fx + fw) * W, (fy + fh) * H,
                outline="#ffd400", width=3,
            )
            canvas.create_text(
                fx * W + 3, fy * H - 2, text=card, fill="#ffd400", anchor="sw",
                font=("Consolas", 14, "bold"),
            )
        for s in state.seats:
            colour = "#00ff66" if s.is_hero else "#ffffff"
            text = s.name or "?"
            if s.stack is not None:
                text += f" {s.stack:g}"
            if s.action:
                text += f" [{s.action}]"
            canvas.create_text(
                s.cx * W, s.cy * H, text=text, fill=colour, anchor="w",
                font=("Consolas", 10, "bold"),
            )
        cards = [c for c, _ in board_located]
        if cards:
            canvas.create_text(
                W * 0.5, H * 0.05, text="BOARD: " + " ".join(cards),
                fill="#00ddff", font=("Consolas", 15, "bold"),
            )

        # Hero hole cards, boxed + labeled at the fixed offset above the nameplate.
        hero = state.hero
        if hero is not None and hero.hole_cards:
            from .cards import hero_card_region

            fx, fy, fw, fh = hero_card_region(hero.cx, hero.cy)
            canvas.create_rectangle(
                fx * W, fy * H, (fx + fw) * W, (fy + fh) * H,
                outline="#00ff66", width=3,
            )
            canvas.create_text(
                fx * W, fy * H - 2, text="YOU: " + " ".join(hero.hole_cards),
                fill="#00ff66", anchor="sw", font=("Consolas", 13, "bold"),
            )
        stake = (
            f"{state.small_blind:g}/{state.big_blind:g}" if state.big_blind else "?"
        )
        pot = f"   pot {state.pot:g}" if state.pot else ""
        canvas.create_text(
            12, H * 0.10, anchor="w", text=f"stakes {stake}{pot}",
            fill="#cccccc", font=("Consolas", 11, "bold"),
        )
        canvas.create_text(
            12, H - 12, anchor="w", fill="#ffcc00",
            text="DETECTIONS ONLY — no advice (post-hand review stays separate)",
            font=("Consolas", 9, "bold"),
        )


def run_overlay(window_substr: str, *, hero_name: str | None = None,
                seconds: float | None = None) -> int:
    return Overlay(window_substr, hero_name=hero_name).run(seconds=seconds)
