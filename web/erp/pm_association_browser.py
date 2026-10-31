"""Real Chromium smoke test of the fictional PM/work-center review form.

Run from repository root after installing Playwright and its Chromium browser:
    python web/erp/pm_association_browser.py
No live systems, production assets, credentials or network services are used.
"""
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
FORM = 'form[data-form="pm-work-center-link"]'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *args: object) -> None:
        pass


def browser_test() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()
                url = f'http://127.0.0.1:{server.server_port}/web/erp/index.html?machine=DEMO-M-001#pm'
                page.goto(url, wait_until="domcontentloaded")
                form = page.locator(FORM)
                form.wait_for(state="visible")
                assert form.locator('input[name="machine"]').input_value() == "DEMO-M-001"
                form.locator('select[name="center"]').select_option("PRESS-02")
                form.locator('input[name="source"]').fill("SYN-BROWSER-001")

                # The actual browser must prevent an unconfirmed form submission.
                assert not form.evaluate("element => element.checkValidity()")
                form.locator('button[type="submit"]').click()
                assert page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return localStorage.getItem(ERP_KEY);
                }""") is None

                form.locator('input[name="confirmed"]').check()
                assert form.evaluate("element => element.checkValidity()")
                form.locator('button[type="submit"]').click()
                page.wait_for_function("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return JSON.parse(localStorage.getItem(ERP_KEY) || 'null')?.pm?.workCenterLinkHistory?.length === 1;
                }""")
                state = page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return JSON.parse(localStorage.getItem(ERP_KEY));
                }""")
                assert state["pm"]["machines"][0]["workCenterLink"]["centerId"] == "PRESS-02"
                assert state["pm"]["workCenterLinkHistory"][0]["sourceRef"] == "SYN-BROWSER-001"
                assert state["events"][-1]["type"] == "pm.work_center.demo_link_reviewed"

                page.reload(wait_until="domcontentloaded")
                form = page.locator(FORM)
                form.wait_for(state="visible")
                assert form.locator('select[name="center"]').input_value() == "PRESS-02"
                assert "SYN-BROWSER-001" in page.locator("#view").inner_text()

                # The real browser's persisted PM state is passed to the existing
                # routing reviewer. Later review must not clear an earlier window.
                evidence = page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    const {assessAlternateCenters} = await import('./routing-capacity-advice.mjs');
                    const state = JSON.parse(localStorage.getItem(ERP_KEY));
                    const scenario = window => ({window, pmContext:{state:state.pm}, centers:[{
                        id:'PRESS-02', routedOperationCount:0,
                        capability:{operation:'Laser cut blank', supported:true, sourceRef:'SYN-CAP-001'},
                        calendarHours:8, bookedHours:0, queuedHours:0, maintenanceHours:0,
                        setupHours:1, runHours:1, capacitySourceRef:'SYN-CALENDAR-001',
                        readinessSourceRef:'SYN-READY-001', maintenanceState:'CLEAR',
                        tooling:'READY', fixture:'READY', material:'READY', deliveryState:'ON_TIME'
                    }]});
                    const job = state.jobs[0];
                    const past = assessAlternateCenters(job, '10', scenario({
                        start:'2020-11-02T08:00:00Z', end:'2020-11-02T16:00:00Z'
                    }));
                    const future = assessAlternateCenters(job, '10', scenario({
                        start:'2099-11-02T08:00:00Z', end:'2099-11-02T16:00:00Z'
                    }));
                    return {past:past.assessments[0].pmEvidence.status,
                        pastSuggestions:past.suggestions.length,
                        futureMachine:future.assessments[0].pmEvidence.machineId,
                        canAutoApply:future.canAutoApply};
                }""")
                assert evidence == {
                    "past": "UNMAPPED", "pastSuggestions": 0,
                    "futureMachine": "DEMO-M-001", "canAutoApply": False,
                }, evidence
                context.close()
                print("PASS: Chromium form confirmation, save, reload and historical routing review")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    browser_test()
