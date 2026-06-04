"""PyInstaller entry point.

A tiny launcher that imports the package and runs the GUI. PyInstaller targets
this file (not the package module directly) so the package's relative imports
resolve normally.
"""

from holdem_coach.app import main

if __name__ == "__main__":
    raise SystemExit(main())
