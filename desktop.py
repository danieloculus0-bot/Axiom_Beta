from __future__ import annotations

import os
import threading
import webbrowser

from waitress import serve
from superforge.app import create_app


def main() -> None:
    host = os.environ.get("AXIOM_HOST") or os.environ.get("SUPERFORGE_HOST", "127.0.0.1")
    port = int(os.environ.get("AXIOM_PORT") or os.environ.get("SUPERFORGE_PORT", "5060"))
    start_path = os.environ.get("AXIOM_START_PATH", "/")
    if not start_path.startswith("/") or start_path.startswith("//"):
        start_path = "/"
    url = f"http://127.0.0.1:{port}{start_path}"
    app = create_app()
    if (os.environ.get("AXIOM_NO_BROWSER") or os.environ.get("SUPERFORGE_NO_BROWSER", "")).strip().lower() not in {"1", "true", "yes"}:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    serve(app, host=host, port=port, threads=8)


if __name__ == "__main__":
    main()
