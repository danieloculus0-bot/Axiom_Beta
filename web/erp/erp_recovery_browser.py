"""Chromium acceptance test for synthetic ERP browser-record recovery.

Runs against a local static HTTP server, never a production backend.
"""
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
ERP_KEY = "axiom_public_erp_suite_v1"
CLOCK_KEY = "axiom_ewi_public_demo_sessions_v1"
WORKFORCE_KEY = "axiom_public_workforce_demo_v1"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *args: object) -> None:
        pass


def run() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                url = f"http://127.0.0.1:{server.server_port}/web/erp/index.html#jobs"
                cases = (
                    ("malformed ERP", ERP_KEY, "{"),
                    ("oversized ERP", ERP_KEY, "x" * 1800000),
                    ("malformed workforce", WORKFORCE_KEY, "{"),
                    ("oversized workforce", WORKFORCE_KEY, "x" * 800000),
                    ("invalid clocks", CLOCK_KEY, "{}"),
                    ("oversized clocks", CLOCK_KEY, "x" * 2500000),
                )
                for name, key, value in cases:
                    context = browser.new_context()
                    try:
                        page = context.new_page()
                        page.goto(url, wait_until="domcontentloaded")
                        page.locator("#view").wait_for(state="visible")
                        page.evaluate("([key, value]) => localStorage.setItem(key, value)", [key, value])
                        page.reload(wait_until="domcontentloaded")
                        notice = page.get_by_role("alert")
                        notice.get_by_role("heading", name="Saved ERP data needs recovery").wait_for()
                        assert page.locator("#view").count() == 0, name
                        assert page.evaluate("key => localStorage.getItem(key)", key) == value, name
                        page.reload(wait_until="domcontentloaded")
                        notice.get_by_role("heading", name="Saved ERP data needs recovery").wait_for()
                        assert page.evaluate("key => localStorage.getItem(key)", key) == value, name
                    finally:
                        context.close()
                # Clean storage must still show the normal fictional UI.
                context = browser.new_context()
                try:
                    page = context.new_page()
                    page.goto(url, wait_until="domcontentloaded")
                    page.locator("#view").wait_for(state="visible")
                    assert page.get_by_role("alert").count() == 0
                    page.reload(wait_until="domcontentloaded")
                    page.locator("#view").wait_for(state="visible")
                finally:
                    context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    run()
    print("ERP recovery Chromium reload acceptance passed")
