"""Desktop GUI panel for the Hold'em Study Coach (Tkinter, stdlib only).

A *post-hand* review panel: open a HandHistory JSON (or pick a bundled sample),
and the computed review appears in a colour-coded panel — leaks in red, sound
plays in green. This is a separate panel, never an on-table overlay, and only
ever shows fully-resolved hands (CLAUDE.md §1).

Monte Carlo equity runs on a worker thread so the window stays responsive; the
result is handed back to the Tk main loop through a queue.

Launch:  python -m holdem_coach gui      (or the packaged HoldemCoach.exe)
"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk

from .analysis.scorer import DecisionAnalysis, score_hand
from .coaching.coach import CoachingNote, coach_decisions, make_anthropic_client
from .handhistory import HandHistory, HandHistoryError

# Tag colours (foreground) keyed by the scorer's short tag.
_TAG_COLOURS = {
    "LEAK": "#c0392b",  # red
    "OK": "#1e8449",    # green
    "THIN": "#b9770e",  # amber
    "INFO": "#566573",  # grey
}
_MARKERS = {"LEAK": "✗", "OK": "✓", "THIN": "≈", "INFO": "·"}


def sample_dir() -> Path:
    """Locate the bundled sample_hands dir, both from source and when frozen."""
    if getattr(sys, "frozen", False):  # PyInstaller one-file/one-dir
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parents[1]
    return base / "sample_hands"


class CoachApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Hold'em Study Coach · post-hand review")
        self.root.geometry("860x680")
        self.root.minsize(640, 480)

        self._q: queue.Queue = queue.Queue()
        self._busy = False
        self._current_path: Path | None = None

        self._build_toolbar()
        self._build_panel()
        self._build_statusbar()

        self.root.after(80, self._poll_queue)
        self._populate_samples()
        self._show_welcome()

    # ---- layout ----------------------------------------------------------- #
    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, padding=(10, 8))
        bar.pack(side=tk.TOP, fill=tk.X)

        self.open_btn = ttk.Button(bar, text="Open hand…", command=self.on_open)
        self.open_btn.pack(side=tk.LEFT)

        ttk.Label(bar, text="  Sample:").pack(side=tk.LEFT)
        self.sample_var = tk.StringVar(value="")
        self.sample_combo = ttk.Combobox(
            bar, textvariable=self.sample_var, state="readonly", width=28
        )
        self.sample_combo.pack(side=tk.LEFT, padx=(2, 10))
        self.sample_combo.bind("<<ComboboxSelected>>", self.on_pick_sample)

        ttk.Label(bar, text="Iterations:").pack(side=tk.LEFT)
        self.iter_var = tk.IntVar(value=8000)
        ttk.Spinbox(
            bar, from_=1000, to=50000, increment=1000, width=7,
            textvariable=self.iter_var,
        ).pack(side=tk.LEFT, padx=(2, 10))

        self.rerun_btn = ttk.Button(
            bar, text="Re-run", command=self.on_rerun, state=tk.DISABLED
        )
        self.rerun_btn.pack(side=tk.LEFT)

        # Opt-in real LLM coaching. Reads ANTHROPIC_API_KEY from the env; off by
        # default so the app always works with no key (mock coaching).
        self.ai_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bar, text="AI coaching", variable=self.ai_var
        ).pack(side=tk.RIGHT)

    def _build_panel(self) -> None:
        frame = ttk.Frame(self.root, padding=(10, 0))
        frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        mono = font.nametofont("TkFixedFont").copy()
        mono.configure(size=11)

        self.text = tk.Text(
            frame, wrap=tk.WORD, font=mono, padx=12, pady=10,
            background="#fbfbfb", foreground="#212f3d", relief=tk.FLAT,
            spacing1=1, spacing3=2,
        )
        scroll = ttk.Scrollbar(frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        bold = mono.copy()
        bold.configure(weight="bold")
        big = mono.copy()
        big.configure(size=13, weight="bold")
        ital = mono.copy()
        ital.configure(slant="italic")

        self.text.tag_configure("h1", font=big, foreground="#1b2631")
        self.text.tag_configure("h2", font=bold)
        self.text.tag_configure("dim", foreground="#7f8c8d")
        self.text.tag_configure("takeaway", font=ital, foreground="#5d6d7e")
        for tag, colour in _TAG_COLOURS.items():
            self.text.tag_configure(tag, foreground=colour, font=bold)
        self.text.configure(state=tk.DISABLED)

    def _build_statusbar(self) -> None:
        self.status = tk.StringVar(value="Ready.")
        bar = ttk.Frame(self.root, padding=(10, 4))
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Separator(self.root).pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(bar, textvariable=self.status, foreground="#566573").pack(
            side=tk.LEFT
        )

    # ---- sample handling -------------------------------------------------- #
    def _populate_samples(self) -> None:
        d = sample_dir()
        self._samples = sorted(d.glob("*.json")) if d.is_dir() else []
        self.sample_combo["values"] = [p.stem for p in self._samples]
        if not self._samples:
            self.sample_combo.configure(state=tk.DISABLED)

    def on_pick_sample(self, _event=None) -> None:
        idx = self.sample_combo.current()
        if 0 <= idx < len(self._samples):
            self.analyze(self._samples[idx])

    # ---- actions ---------------------------------------------------------- #
    def on_open(self) -> None:
        initial = sample_dir()
        path = filedialog.askopenfilename(
            title="Open a HandHistory JSON",
            initialdir=str(initial if initial.is_dir() else Path.home()),
            filetypes=[("HandHistory JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.sample_var.set("")
            self.analyze(Path(path))

    def on_rerun(self) -> None:
        if self._current_path is not None:
            self.analyze(self._current_path)

    def analyze(self, path: Path) -> None:
        if self._busy:
            return
        self._current_path = path
        self._busy = True
        self._set_controls(tk.DISABLED)
        self.status.set(f"Analyzing {path.name}…")
        iterations = max(1000, int(self.iter_var.get() or 8000))
        use_llm = bool(self.ai_var.get())
        worker = threading.Thread(
            target=self._worker, args=(path, iterations, use_llm), daemon=True
        )
        worker.start()

    def _worker(self, path: Path, iterations: int, use_llm: bool) -> None:
        try:
            hh = HandHistory.load(path)
            decisions = score_hand(hh, iterations=iterations, seed=1234)
            # Building the client + the API call both happen here, off the UI
            # thread, so the window never freezes during the network round-trip.
            client = make_anthropic_client() if use_llm else None
            notes = coach_decisions(decisions, client=client)
            self._q.put(("ok", path, hh, decisions, notes))
        except Exception as exc:  # surfaced to the user in the main thread
            self._q.put(("err", path, exc))

    # ---- main-thread queue pump ------------------------------------------ #
    def _poll_queue(self) -> None:
        try:
            while True:
                item = self._q.get_nowait()
                if item[0] == "ok":
                    _, path, hh, decisions, notes = item
                    self._render(hh, decisions, notes)
                    leaks = sum(1 for d in decisions if d.leak)
                    verdict = (
                        f"{leaks} leak(s)" if leaks else "no clear leaks"
                    )
                    self.status.set(f"{path.name} — {len(decisions)} decisions, {verdict}.")
                else:
                    _, path, exc = item
                    self._render_error(path, exc)
                    self.status.set(f"Error reading {path.name}.")
                self._busy = False
                self._set_controls(tk.NORMAL)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_queue)

    def _set_controls(self, state: str) -> None:
        self.open_btn.configure(state=state)
        # Re-run only makes sense once a hand is loaded.
        self.rerun_btn.configure(
            state=(state if self._current_path is not None else tk.DISABLED)
        )
        combo_state = "readonly" if (state == tk.NORMAL and self._samples) else tk.DISABLED
        self.sample_combo.configure(state=combo_state)

    # ---- rendering -------------------------------------------------------- #
    def _write(self, content: str, *tags: str) -> None:
        self.text.insert(tk.END, content, tags)

    def _begin(self) -> None:
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

    def _end(self) -> None:
        self.text.configure(state=tk.DISABLED)
        self.text.see("1.0")

    def _show_welcome(self) -> None:
        self._begin()
        self._write("Hold'em Study Coach\n", "h1")
        self._write(
            "Post-hand review only — no real-time assistance, no overlay.\n\n",
            "dim",
        )
        self._write(
            "Open a HandHistory JSON, or pick a bundled sample above to begin.\n",
        )
        self._end()

    def _render(
        self,
        hh: HandHistory,
        decisions: list[DecisionAnalysis],
        notes: list[CoachingNote],
    ) -> None:
        self._begin()
        self._write(f"POST-HAND REVIEW  ·  {hh.hand_id}\n", "h1")
        self._write(
            f"Hero: seat {hh.hero_seat} ({hh.hero_position})  "
            f"{' '.join(hh.hero_hole_cards)}    "
            f"{hh.table.max_seats}-max  blinds "
            f"{hh.table.small_blind:g}/{hh.table.big_blind:g}\n",
        )
        board = hh.board.all_cards()
        if board:
            self._write(f"Board: {' '.join(board)}\n", "dim")
        self._write(
            f"Result: pot {hh.result.pot:g}, hero net "
            f"{hh.result.hero_net:+g}  (winners: seats {hh.result.winning_seats})\n\n",
            "dim",
        )

        if not decisions:
            self._write("No hero decisions found in this hand.\n")
            self._end()
            return

        leaks = 0
        for i, (d, note) in enumerate(zip(decisions, notes), start=1):
            if d.leak:
                leaks += 1
            marker = _MARKERS.get(d.tag, "·")
            board_str = " ".join(d.board) if d.board else "(preflop)"
            self._write(
                f"[{i}] {marker} {d.street.upper()}   {d.hero_class}   ", d.tag
            )
            self._write(f"board {board_str}\n", "dim")

            action_line = f"     action: {d.hero_action}"
            if d.hero_amount:
                action_line += f" {d.hero_amount:g}"
            self._write(action_line + "\n")

            nums = f"     equity ~{d.equity:.0%}  (vs {d.villain_desc})"
            if d.facing_bet:
                nums += (
                    f"   |   to call {d.to_call:g} into {d.pot_before:g} "
                    f"→ need {d.required_equity:.0%}"
                )
                if d.ev_call is not None:
                    nums += f"   |   EV(call) {d.ev_call:+.2f}"
            self._write(nums + "\n", "dim")

            self._write(f"     coach [{note.concept}]: ", "h2")
            self._write(note.explanation + "\n")
            self._write(f"     → {note.takeaway}\n\n", "takeaway")

        summary_tag = "LEAK" if leaks else "OK"
        verdict = f"{leaks} leak(s) flagged." if leaks else "No clear leaks — standard line."
        self._write(
            f"SUMMARY: {len(decisions)} hero decision(s).  {verdict}\n", summary_tag
        )
        self._end()

    def _render_error(self, path: Path, exc: Exception) -> None:
        self._begin()
        kind = "Invalid hand history" if isinstance(exc, HandHistoryError) else "Could not read file"
        self._write(f"{kind}\n", "LEAK")
        self._write(f"{path}\n\n", "dim")
        self._write(f"{exc}\n")
        self._end()
        messagebox.showerror("Hold'em Study Coach", f"{kind}:\n{exc}")


def main(argv: list[str] | None = None) -> int:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")  # native-ish on Windows; falls back below
    except tk.TclError:
        pass
    CoachApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
