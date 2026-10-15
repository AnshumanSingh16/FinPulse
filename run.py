"""Start FinPilot: python run.py  (then open http://localhost:8000 — it opens automatically)."""

from __future__ import annotations

import argparse
import threading
import webbrowser


def main() -> None:
    p = argparse.ArgumentParser(description="Run FinPilot locally.")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 to open it from your phone on the same Wi-Fi.")
    p.add_argument("--no-browser", action="store_true")
    a = p.parse_args()

    import uvicorn

    from finpilot.api.server import STATIC, create_app

    if not STATIC.exists():
        raise SystemExit("The web app isn't built. Run: cd web && npm install && npm run build")
    url = f"http://localhost:{a.port}"
    print(f"\n  FinPilot is running at {url}\n  Press Ctrl+C to stop.\n")
    if not a.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(), host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
