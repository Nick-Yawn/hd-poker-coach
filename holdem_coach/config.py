"""Minimal, dependency-free ``.env`` loader.

Looks for a ``.env`` file (the user's, gitignored) and loads ``KEY=VALUE`` lines
into ``os.environ`` *without* overriding variables already set in the real
environment. Used so secrets like ``ANTHROPIC_API_KEY`` can live in a local file
instead of being exported every session.

Format: one ``KEY=VALUE`` per line; ``#`` comments and blank lines ignored;
surrounding single/double quotes on the value are stripped; an optional leading
``export`` is tolerated.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _candidate_paths() -> list[Path]:
    paths = [Path.cwd() / ".env"]
    if getattr(sys, "frozen", False):  # next to the packaged .exe
        paths.append(Path(sys.executable).resolve().parent / ".env")
    else:  # project root, when running from source
        paths.append(Path(__file__).resolve().parents[1] / ".env")
    # De-dup while preserving order.
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key:
            values[key] = val
    return values


def load_dotenv(*, override: bool = False) -> Path | None:
    """Load the first ``.env`` found. Returns its path, or None if none found.

    Existing ``os.environ`` entries win unless ``override=True``.
    """
    for path in _candidate_paths():
        try:
            # utf-8-sig tolerates a leading BOM, which Windows editors and
            # PowerShell's `Set-Content -Encoding utf8` add — otherwise the
            # first key name would be silently corrupted.
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        for key, val in _parse(text).items():
            if override or key not in os.environ:
                os.environ[key] = val
        return path
    return None
