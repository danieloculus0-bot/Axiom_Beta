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
                # Reassign using the actual form, not a direct state mutation.
                form = page.locator(FORM)
                form.locator('select[name="center"]').select_option("DEMO-CUT")
                form.locator('input[name="source"]').fill("SYN-BROWSER-002")
                form.locator('input[name="confirmed"]').check()
                form.locator('button[type="submit"]').click()
                page.wait_for_function("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return JSON.parse(localStorage.getItem(ERP_KEY) || 'null')
                        ?.pm?.workCenterLinkHistory?.length === 2;
                }""")
                reassigned = page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    const {assessAlternateCenters} = await import('./routing-capacity-advice.mjs');
                    const state = JSON.parse(localStorage.getItem(ERP_KEY));
                    const assess = center => assessAlternateCenters(state.jobs[0], '10', {
                        window:{start:'2099-11-02T08:00:00Z', end:'2099-11-02T16:00:00Z'},
                        pmContext:{state:state.pm}, centers:[{
                            id:center,routedOperationCount:0,
                            capability:{operation:'Laser cut blank',supported:true,sourceRef:'SYN-CAP-001'},
                            calendarHours:8,bookedHours:0,queuedHours:0,maintenanceHours:0,
                            setupHours:1,runHours:1,capacitySourceRef:'SYN-CALENDAR-001',
                            readinessSourceRef:'SYN-READY-001',maintenanceState:'CLEAR',
                            tooling:'READY',fixture:'READY',material:'READY',deliveryState:'ON_TIME'
                        }]
                    }).assessments[0].pmEvidence;
                    return {
                        center:state.pm.machines[0].workCenterLink?.centerId,
                        previous:state.pm.workCenterLinkHistory[1].previousCenterId,
                        event:state.events.at(-1).type,
                        oldStatus:assess('PRESS-02').status,
                        newMachine:assess('DEMO-CUT').machineId
                    };
                }""")
                assert reassigned == {
                    "center": "DEMO-CUT", "previous": "PRESS-02",
                    "event": "pm.work_center.demo_link_reviewed",
                    "oldStatus": "UNMAPPED", "newMachine": "DEMO-M-001",
                }, reassigned
                page.reload(wait_until="domcontentloaded")
                form = page.locator(FORM)
                form.wait_for(state="visible")
                assert form.locator('select[name="center"]').input_value() == "DEMO-CUT"
                assert "SYN-BROWSER-002" in page.locator("#view").inner_text()

                # Explicit unlink must persist, retain both previous reviews,
                # and remove current PM mapping evidence from routing proposals.
                form.locator('select[name="center"]').select_option("")
                form.locator('input[name="source"]').fill("SYN-BROWSER-003")
                form.locator('input[name="confirmed"]').check()
                form.locator('button[type="submit"]').click()
                page.wait_for_function("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return JSON.parse(localStorage.getItem(ERP_KEY) || 'null')
                        ?.pm?.workCenterLinkHistory?.length === 3;
                }""")
                unlinked = page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    const {assessAlternateCenters} = await import('./routing-capacity-advice.mjs');
                    const state = JSON.parse(localStorage.getItem(ERP_KEY));
                    const result = assessAlternateCenters(state.jobs[0], '10', {
                        window:{start:'2099-11-02T08:00:00Z',end:'2099-11-02T16:00:00Z'},
                        pmContext:{state:state.pm},centers:[{
                            id:'DEMO-CUT',routedOperationCount:0,
                            capability:{operation:'Laser cut blank',supported:true,sourceRef:'SYN-CAP-001'},
                            calendarHours:8,bookedHours:0,queuedHours:0,maintenanceHours:0,
                            setupHours:1,runHours:1,capacitySourceRef:'SYN-CALENDAR-001',
                            readinessSourceRef:'SYN-READY-001',maintenanceState:'CLEAR',
                            tooling:'READY',fixture:'READY',material:'READY',deliveryState:'ON_TIME'
                        }]
                    });
                    return {
                        linked:'workCenterLink' in state.pm.machines[0],
                        previous:state.pm.workCenterLinkHistory[2].previousCenterId,
                        current:state.pm.workCenterLinkHistory[2].centerId,
                        kind:state.pm.workCenterLinkHistory[2].kind,
                        event:state.events.at(-1).type,
                        pmStatus:result.assessments[0].pmEvidence.status,
                        suggestions:result.suggestions.length
                    };
                }""")
                assert unlinked == {
                    "linked": False, "previous": "DEMO-CUT", "current": None,
                    "kind": "DEMO_UNLINK", "event": "pm.work_center.demo_unlinked",
                    "pmStatus": "UNMAPPED", "suggestions": 0,
                }, unlinked
                page.reload(wait_until="domcontentloaded")
                form = page.locator(FORM)
                form.wait_for(state="visible")
                assert form.locator('select[name="center"]').input_value() == ""
                assert "UNMAPPED" in page.locator("#view").inner_text()
                assert all(ref in page.locator("#view").inner_text() for ref in (
                    "SYN-BROWSER-001", "SYN-BROWSER-002", "SYN-BROWSER-003"
                ))
                # The routing screen now calls the existing capacity reviewer
                # without supplying fictional availability or capability facts.
                page.goto(url.replace("#pm", "#routing"), wait_until="domcontentloaded")
                capacity_form = page.locator('form[data-form="routing-capacity-review"]')
                capacity_form.wait_for(state="visible")
                capacity_form.locator('select[name="step"]').select_option("10")
                capacity_form.locator('select[name="center"]').select_option("DEMO-CUT")
                capacity_form.locator('input[name="window-start"]').fill("2026-11-02T08:00")
                capacity_form.locator('input[name="window-end"]').fill("2026-11-02T16:00")
                before = page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return localStorage.getItem(ERP_KEY);
                }""")
                capacity_form.locator('button[type="submit"]').click()
                result = page.locator("#routing-capacity-result")
                result.wait_for(state="visible")
                review_text = result.inner_text()
                assert "NEEDS_REVIEW" in review_text, review_text
                assert "UNMAPPED" in review_text, review_text
                assert "Planning-window hours are UNKNOWN" in review_text, review_text
                assert "No alternate routing proposed or saved" in review_text, review_text
                after = page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return localStorage.getItem(ERP_KEY);
                }""")
                assert before == after, "Read-only review must not persist or mutate the ERP"
                page.reload(wait_until="domcontentloaded")
                assert page.locator("#routing-capacity-result").count() == 0, (
                    "Ephemeral evidence review must not be misrepresented as saved"
                )
                # Exercise the new optional scenario through real Chromium inputs.
                # These are entirely fictional, manually asserted estimates.
                capacity_form = page.locator('form[data-form="routing-capacity-review"]')
                capacity_form.locator('details summary').click()
                capacity_form.locator('input[name="scenario-enabled"]').check()
                capacity_form.locator('select[name="scenario-capability"]').select_option("supported")
                for name, value in {
                    "capability-ref": "SYN-BROWSER-CAP-001",
                    "calendarHours": "8",
                    "bookedHours": "1",
                    "queuedHours": "1",
                    "maintenanceHours": "0",
                    "setupHours": "1",
                    "runHours": "2",
                    "capacity-ref": "SYN-BROWSER-CALENDAR-001",
                    "readiness-ref": "SYN-BROWSER-READY-001",
                    "routedOperationCount": "0",
                }.items():
                    capacity_form.locator(f'input[name="scenario-{name}"]').fill(value)
                for name, value in {
                    "maintenanceState": "CLEAR",
                    "tooling": "READY",
                    "fixture": "READY",
                    "material": "READY",
                    "deliveryState": "ON_TIME",
                }.items():
                    capacity_form.locator(f'select[name="scenario-{name}"]').select_option(value)
                capacity_form.locator('select[name="step"]').select_option("10")
                capacity_form.locator('select[name="center"]').select_option("DEMO-CUT")
                capacity_form.locator('input[name="window-start"]').fill("2026-11-02T08:00")
                capacity_form.locator('input[name="window-end"]').fill("2026-11-02T16:00")
                assert capacity_form.evaluate("element => element.checkValidity()")
                scenario_before = page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return localStorage.getItem(ERP_KEY);
                }""")
                capacity_form.locator('button[type="submit"]').click()
                scenario_result = page.locator("#routing-capacity-result")
                scenario_result.wait_for(state="visible")
                scenario_text = scenario_result.inner_text()
                for expected in (
                    "NEEDS_REVIEW", "UNMAPPED", "available 6 hours",
                    "required 3 hours", "utilization 25%",
                    "SYN-BROWSER-CAP-001", "SYN-BROWSER-CALENDAR-001",
                    "SYN-BROWSER-READY-001", "No alternate routing proposed or saved",
                ):
                    assert expected in scenario_text, (expected, scenario_text)
                assert capacity_form.locator('input[name="scenario-enabled"]').is_checked()
                assert capacity_form.locator('input[name="scenario-calendarHours"]').input_value() == "8"
                scenario_after = page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return localStorage.getItem(ERP_KEY);
                }""")
                assert scenario_before == scenario_after, "Scenario review must not write ERP state"

                # An empty hour is UNKNOWN, never silently interpreted as zero.
                capacity_form.locator('input[name="scenario-calendarHours"]').fill("")
                capacity_form.locator('button[type="submit"]').click()
                rejected_message = page.locator("#flash").inner_text()
                assert "All six scenario hour estimates must be explicitly supplied" in rejected_message, rejected_message
                assert page.locator("#flash").get_attribute("role") == "alert"
                # Failed validation must not erase the user's unsaved scenario.
                assert capacity_form.locator('input[name="scenario-enabled"]').is_checked()
                assert capacity_form.locator("details").get_attribute("open") is not None
                assert capacity_form.locator('select[name="step"]').input_value() == "10"
                assert capacity_form.locator('select[name="center"]').input_value() == "DEMO-CUT"
                assert capacity_form.locator('input[name="window-start"]').input_value() == "2026-11-02T08:00"
                assert capacity_form.locator('input[name="scenario-bookedHours"]').input_value() == "1"
                assert capacity_form.locator('input[name="scenario-capacity-ref"]').input_value() == "SYN-BROWSER-CALENDAR-001"
                assert capacity_form.locator('select[name="scenario-material"]').input_value() == "READY"
                assert capacity_form.locator('input[name="scenario-calendarHours"]').input_value() == ""
                # Correct the invalid field in place and verify normal review recovers.
                capacity_form.locator('input[name="scenario-calendarHours"]').fill("8")
                capacity_form.locator('button[type="submit"]').click()
                assert "available 6 hours" in page.locator("#routing-capacity-result").inner_text()
                assert page.locator("#flash").get_attribute("role") == "status"
                assert scenario_before == page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return localStorage.getItem(ERP_KEY);
                }"""), "Rejected scenario must not write ERP state"

                page.reload(wait_until="domcontentloaded")
                assert page.locator("#routing-capacity-result").count() == 0
                capacity_form = page.locator('form[data-form="routing-capacity-review"]')
                assert not capacity_form.locator('input[name="scenario-enabled"]').is_checked()
                assert capacity_form.locator('input[name="scenario-calendarHours"]').input_value() == ""
                assert capacity_form.locator('input[name="scenario-capability-ref"]').input_value() == ""

                # Capacity reviews are ephemeral. A same-job clock session changes
                # routing-editor eligibility and must invalidate an older review,
                # even when navigating between screens without a page reload.
                capacity_form.locator('select[name="step"]').select_option("10")
                capacity_form.locator('select[name="center"]').select_option("DEMO-CUT")
                capacity_form.locator('input[name="window-start"]').fill("2026-11-02T08:00")
                capacity_form.locator('input[name="window-end"]').fill("2026-11-02T16:00")
                capacity_form.locator('button[type="submit"]').click()
                assert page.locator("#routing-capacity-result").count() == 1
                page.evaluate("location.hash='#ewi'")
                page.locator('[data-action="clock-in"]').wait_for(state="visible")
                page.evaluate("location.hash='#routing'")
                assert page.locator("#routing-capacity-result").count() == 1, (
                    "Navigation alone must not erase a review"
                )
                page.evaluate("location.hash='#ewi'")
                page.locator('[data-action="clock-in"]').click()
                page.evaluate("location.hash='#routing'")
                assert page.locator("#routing-capacity-result").count() == 0, (
                    "Clock IN must invalidate stale routing eligibility"
                )
                capacity_form = page.locator('form[data-form="routing-capacity-review"]')
                capacity_form.locator('select[name="step"]').select_option("10")
                capacity_form.locator('select[name="center"]').select_option("DEMO-CUT")
                capacity_form.locator('input[name="window-start"]').fill("2026-11-02T08:00")
                capacity_form.locator('input[name="window-end"]').fill("2026-11-02T16:00")
                capacity_form.locator('button[type="submit"]').click()
                assert "Browser-local EWI clock sessions on this job: 1" in (
                    page.locator("#routing-capacity-result").inner_text()
                )
                page.evaluate("location.hash='#ewi'")
                page.locator('[data-action="clock-out"]').click()
                page.evaluate("location.hash='#routing'")
                assert page.locator("#routing-capacity-result").count() == 0, (
                    "Clock OUT must invalidate stale routing evidence"
                )
                context.close()
                print("PASS: Chromium PM lifecycle and read-only routing capacity scenario")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    browser_test()
