"""Windows-friendly entrypoint — no PYTHONPATH needed.

Usage:
  setup.bat
  run.bat
  or:  python start.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure working directory is project root (so config.yaml / .env resolve)
import os

os.chdir(ROOT)

from shadow.main import run  # noqa: E402

if __name__ == "__main__":
    run()