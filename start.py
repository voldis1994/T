"""Windows-friendly entrypoint — no PYTHONPATH needed.

Usage:
  setup.bat
  start.bat
  or:  python start.py
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)


def _open_dashboard(port: int, delay: float = 1.5) -> None:
    url = f"http://127.0.0.1:{port}/"
    print(f"\n>>> Dashboard: {url}\n>>> (ne htpp — http)\n", flush=True)

    def _later() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception as exc:  # noqa: BLE001
            print(f"Neizdevas atvert parlukprogrammu: {exc}", flush=True)

    threading.Thread(target=_later, daemon=True).start()


def main() -> None:
    from shadow.config import settings
    from shadow.main import run

    _open_dashboard(int(settings.shadow_port))
    run()


if __name__ == "__main__":
    main()