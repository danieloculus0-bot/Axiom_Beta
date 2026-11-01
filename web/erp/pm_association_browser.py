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
                # Missing booked/queued evidence is UNKNOWN, not automatically zero.
                capacity_form.locator('input[name="scenario-bookedHours"]').fill("")
                capacity_form.locator('input[name="scenario-queuedHours"]').fill("")
                capacity_form.locator('button[type="submit"]').click()
                unknown_text = page.locator("#routing-capacity-result").inner_text()
                assert "Planning-window hours are UNKNOWN" in unknown_text, unknown_text
                assert "available UNKNOWN hours" in unknown_text, unknown_text
                assert "utilization UNKNOWN%" in unknown_text, unknown_text
                capacity_form.locator('input[name="scenario-bookedHours"]').fill("1")
                capacity_form.locator('input[name="scenario-queuedHours"]').fill("1")
                capacity_form.locator('button[type="submit"]').click()
                assert "available 6 hours" in page.locator("#routing-capacity-result").inner_text()
                # A changed scenario input must clear its old assessment without losing
                # unsaved values or modifying canonical fictional ERP records.
                capacity_form.locator('input[name="scenario-bookedHours"]').fill("2")
                assert page.locator("#routing-capacity-result").count() == 0
                assert "Submit again" in page.locator("#routing-capacity-stale").inner_text()
                assert capacity_form.locator('input[name="scenario-bookedHours"]').input_value() == "2"
                capacity_form.locator('button[type="submit"]').click()
                assert "available 5 hours" in page.locator("#routing-capacity-result").inner_text()
                # Select changes must invalidate the prior assessment too.
                capacity_form.locator('select[name="scenario-tooling"]').select_option("BLOCKED")
                assert page.locator("#routing-capacity-result").count() == 0
                capacity_form.locator('button[type="submit"]').click()
                assert "EXCLUDED" in page.locator("#routing-capacity-result").inner_text()
                capacity_form.locator('select[name="scenario-tooling"]').select_option("READY")
                assert page.locator("#routing-capacity-result").count() == 0
                capacity_form.locator('input[name="scenario-bookedHours"]').fill("1")
                capacity_form.locator('button[type="submit"]').click()
                assert "available 6 hours" in page.locator("#routing-capacity-result").inner_text()
                assert scenario_before == page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return localStorage.getItem(ERP_KEY);
                }"""), "Scenario edits must not write fictional ERP records"

                # An empty hour is UNKNOWN, never silently interpreted as zero.
                capacity_form.locator('input[name="scenario-calendarHours"]').fill("")
                capacity_form.locator('button[type="submit"]').click()
                rejected_message = page.locator("#flash").inner_text()
                assert "Calendar, maintenance, setup and run hours must be explicitly supplied" in rejected_message, rejected_message
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

                # Browser-level regression for conservative placeholder scenarios.
                # A placeholder is a labeled assumption, never a scheduled job.
                capacity_form.locator('input[name="scenario-placeholder"]').check()
                for field in ("calendarHours", "bookedHours", "queuedHours"):
                    capacity_form.locator(f'input[name="scenario-{field}"]').fill("")
                capacity_form.locator('button[type="submit"]').click()
                placeholder_text = page.locator("#routing-capacity-result").inner_text()
                for expected in (
                    "PLACEHOLDER_ASSISTED",
                    "calendarHours: PLACEHOLDER",
                    "bookedHours: PLACEHOLDER",
                    "queuedHours: PLACEHOLDER",
                    "available 3.75 hours",
                    "utilization 37.5%",
                    "No alternate routing proposed or saved",
                ):
                    assert expected in placeholder_text, (expected, placeholder_text)
                assert capacity_form.locator('input[name="scenario-calendarHours"]').input_value() == ""

                # A planner can edit the fictional interruption allowance. A
                # larger buffer must reduce provisional hours, not fabricate
                # availability or change any canonical ERP record.
                buffer_field = capacity_form.locator('input[name="scenario-bufferPercent"]')
                assert buffer_field.input_value() == "25"
                buffer_field.fill("50")
                capacity_form.locator('button[type="submit"]').click()
                cautious_text = page.locator("#routing-capacity-result").inner_text()
                for expected in (
                    "EXCLUDED", "available 2.5 hours",
                    "calendarHours: PLACEHOLDER", "50% interruption allowance",
                    "No alternate routing proposed or saved",
                ):
                    assert expected in cautious_text, (expected, cautious_text)
                assert buffer_field.input_value() == "50"
                buffer_field.fill("25")
                capacity_form.locator('button[type="submit"]').click()
                assert "available 3.75 hours" in page.locator("#routing-capacity-result").inner_text()

                # An explicit planner override changes only that field's origin.
                capacity_form.locator('input[name="scenario-bookedHours"]').fill("1")
                capacity_form.locator('button[type="submit"]').click()
                mixed_text = page.locator("#routing-capacity-result").inner_text()
                for expected in (
                    "calendarHours: PLACEHOLDER",
                    "bookedHours: MANUAL",
                    "queuedHours: PLACEHOLDER",
                    "available 4.25 hours",
                ):
                    assert expected in mixed_text, (expected, mixed_text)

                # Reset to unknown rather than silently treating blanks as zero.
                capacity_form.locator('input[name="scenario-placeholder"]').uncheck()
                capacity_form.locator('input[name="scenario-calendarHours"]').fill("8")
                capacity_form.locator('input[name="scenario-bookedHours"]').fill("")
                capacity_form.locator('input[name="scenario-queuedHours"]').fill("")
                capacity_form.locator('button[type="submit"]').click()
                unknown_origin_text = page.locator("#routing-capacity-result").inner_text()
                for expected in (
                    "calendarHours: MANUAL",
                    "bookedHours: UNKNOWN",
                    "queuedHours: UNKNOWN",
                    "available UNKNOWN hours",
                    "utilization UNKNOWN%",
                ):
                    assert expected in unknown_origin_text, (expected, unknown_origin_text)
                assert scenario_before == page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return localStorage.getItem(ERP_KEY);
                }"""), "Placeholder, manual and unknown reviews must not write ERP state"

                page.reload(wait_until="domcontentloaded")
                assert page.locator("#routing-capacity-result").count() == 0
                capacity_form = page.locator('form[data-form="routing-capacity-review"]')
                assert not capacity_form.locator('input[name="scenario-enabled"]').is_checked()
                assert capacity_form.locator('input[name="scenario-calendarHours"]').input_value() == ""
                assert capacity_form.locator('input[name="scenario-capability-ref"]').input_value() == ""

                # An unsaved routing draft must invalidate the prior saved-route
                # assessment. A new review must not use canonical operations while
                # the visible editor is working on a different unsaved sequence.
                capacity_form.locator('select[name="step"]').select_option("10")
                capacity_form.locator('select[name="center"]').select_option("DEMO-CUT")
                capacity_form.locator('input[name="window-start"]').fill("2026-11-02T08:00")
                capacity_form.locator('input[name="window-end"]').fill("2026-11-02T16:00")
                capacity_form.locator('button[type="submit"]').click()
                assert page.locator("#routing-capacity-result").count() == 1
                draft_before = page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return localStorage.getItem(ERP_KEY);
                }""")
                page.locator('[data-action="routing-start"]').click()
                assert page.locator("#routing-editor-form").count() == 1
                assert page.locator("#routing-capacity-result").count() == 0, (
                    "Opening an unsaved routing draft must invalidate prior capacity evidence"
                )
                capacity_form = page.locator('form[data-form="routing-capacity-review"]')
                capacity_form.locator('select[name="step"]').select_option("10")
                capacity_form.locator('select[name="center"]').select_option("DEMO-CUT")
                capacity_form.locator('input[name="window-start"]').fill("2026-11-02T08:00")
                capacity_form.locator('input[name="window-end"]').fill("2026-11-02T16:00")
                capacity_form.locator('button[type="submit"]').click()
                assert "Save or cancel unsaved routing edits" in page.locator("#flash").inner_text()
                assert page.locator("#routing-capacity-result").count() == 0
                # A real unsaved reorder remains in the draft editor only.
                page.locator('[data-action="routing-down"][data-index="0"]').click()
                assert page.locator("#routing-capacity-result").count() == 0
                page.locator('[data-action="routing-cancel"]').click()
                assert page.locator("#routing-editor-form").count() == 0
                assert page.locator("#routing-capacity-result").count() == 0
                assert draft_before == page.evaluate("""async () => {
                    const {ERP_KEY} = await import('./engine.mjs');
                    return localStorage.getItem(ERP_KEY);
                }"""), "Unsaved draft review and cancellation must not write ERP state"

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
                page.locator('form[data-form="routing-capacity-review"]').wait_for(state="visible")
                assert page.locator("#routing-capacity-result").count() == 1, (
                    "Navigation alone must not erase a review"
                )
                page.evaluate("location.hash='#ewi'")
                page.locator('[data-action="clock-in"]').click()
                page.evaluate("location.hash='#routing'")
                page.locator('form[data-form="routing-capacity-review"]').wait_for(state="visible")
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
                page.locator('form[data-form="routing-capacity-review"]').wait_for(state="visible")
                assert page.locator("#routing-capacity-result").count() == 0, (
                    "Clock OUT must invalidate stale routing evidence"
                )

                # Chromium handoff: explicit cancel and save using only the
                # existing fictional PM, capacity and routing UI controls.
                # This second browser context starts from untouched demo data.
                handoff_context = browser.new_context()
                try:
                    handoff_page = handoff_context.new_page()
                    handoff_page.goto(url, wait_until="domcontentloaded")
                    pm_completion = handoff_page.locator('form[data-form="pm-complete"]')
                    pm_completion.wait_for(state="visible")
                    pm_completion.locator('select[name="task"]').select_option("DEMO-PM-001")
                    pm_completion.locator('input[name="confirmed"]').check()
                    pm_completion.locator('button[type="submit"]').click()
                    assert handoff_page.evaluate("""async () => {
                        const {ERP_KEY} = await import('./engine.mjs');
                        const pm = JSON.parse(localStorage.getItem(ERP_KEY)).pm;
                        return pm.completions[0]?.id === 'DEMO-COMP-0001' &&
                            pm.completions[0]?.taskId === 'DEMO-PM-001' &&
                            pm.completions[0]?.result === 'PASS';
                    }"""), handoff_page.locator("#flash").inner_text()

                    pm_link = handoff_page.locator(FORM)
                    pm_link.locator('select[name="center"]').select_option("DEMO-CUT")
                    pm_link.locator('input[name="source"]').fill("SYN-HANDOFF-PM-001")
                    pm_link.locator('input[name="confirmed"]').check()
                    pm_link.locator('button[type="submit"]').click()
                    assert "DEMO-CUT" in handoff_page.locator("#view").inner_text()

                    handoff_page.evaluate("location.hash='#routing'")
                    handoff_page.locator('form[data-form="routing-capacity-review"]').wait_for(state="visible")

                    def review_eligible_handoff(
                        expect_eligible: bool = True, target_page=None,
                        expected_blocker: str = "PM requests overlapping the planning window",
                    ) -> None:
                        target = target_page or handoff_page
                        form = target.locator('form[data-form="routing-capacity-review"]')
                        details = form.locator("details")
                        if details.get_attribute("open") is None:
                            details.locator("summary").click()
                        form.locator('input[name="scenario-enabled"]').check()
                        form.locator('select[name="scenario-capability"]').select_option("supported")
                        for name, value in {
                            "capability-ref": "SYN-HANDOFF-CAP-001",
                            "calendarHours": "8", "bookedHours": "1",
                            "queuedHours": "1", "maintenanceHours": "0",
                            "setupHours": "1", "runHours": "2",
                            "capacity-ref": "SYN-HANDOFF-CAL-001",
                            "readiness-ref": "SYN-HANDOFF-READY-001",
                            "routedOperationCount": "0",
                        }.items():
                            form.locator(f'input[name="scenario-{name}"]').fill(value)
                        for name, value in {
                            "maintenanceState": "CLEAR", "tooling": "READY",
                            "fixture": "READY", "material": "READY",
                            "deliveryState": "ON_TIME",
                        }.items():
                            form.locator(f'select[name="scenario-{name}"]').select_option(value)
                        form.locator('select[name="step"]').select_option("10")
                        form.locator('select[name="center"]').select_option("DEMO-CUT")
                        form.locator('input[name="window-start"]').fill("2026-11-02T08:00")
                        form.locator('input[name="window-end"]').fill("2026-11-02T16:00")
                        assert form.evaluate("element => element.checkValidity()")
                        form.locator('button[type="submit"]').click()
                        result = target.locator("#routing-capacity-result")
                        if expect_eligible:
                            assert "SCENARIO_ELIGIBLE" in result.inner_text(), result.inner_text()
                            target.locator(
                                '[data-action="routing-use-capacity-draft"]'
                            ).wait_for(state="visible")
                        else:
                            assert "NEEDS_REVIEW" in result.inner_text(), result.inner_text()
                            assert expected_blocker in result.inner_text()
                            assert target.locator(
                                '[data-action="routing-use-capacity-draft"]'
                            ).count() == 0

                    def stored_routing():
                        return handoff_page.evaluate("""async () => {
                            const {ERP_KEY} = await import('./engine.mjs');
                            const state = JSON.parse(localStorage.getItem(ERP_KEY));
                            return {
                                raw: localStorage.getItem(ERP_KEY),
                                routing: state.jobs[0].routing,
                                events: state.events.map(event => event.type)
                            };
                        }""")

                    review_eligible_handoff()
                    original = stored_routing()
                    assert original["routing"]["operations"][0]["center"] == "LASER-01"
                    handoff_page.locator('[data-action="routing-use-capacity-draft"]').click()
                    editor = handoff_page.locator("#routing-editor-form")
                    assert editor.count() == 1
                    assert editor.locator('select[name="center-0"]').input_value() == "DEMO-CUT"
                    assert "UNSAVED scenario suggestion" in handoff_page.locator("#view").inner_text()
                    assert handoff_page.locator("#routing-capacity-result").count() == 0
                    assert stored_routing()["raw"] == original["raw"], (
                        "Opening a proposed routing must not persist it"
                    )
                    handoff_page.locator('[data-action="routing-cancel"]').click()
                    assert handoff_page.locator("#routing-editor-form").count() == 0
                    assert stored_routing()["raw"] == original["raw"], (
                        "Cancel must leave canonical routing and event history unchanged"
                    )

                    # A new fictional maintenance request for the linked machine
                    # must invalidate a previously eligible alternate. Review the
                    # same scenario while the request is open, then close it through
                    # the PM UI. Closing is not itself an approval or routing edit.
                    review_eligible_handoff()
                    before_request = stored_routing()
                    handoff_page.evaluate("location.hash='#pm'")
                    maintenance_form = handoff_page.locator('form[data-form="pm-request"]')
                    maintenance_form.wait_for(state="visible")
                    maintenance_form.locator('select[name="machine"]').select_option("DEMO-M-001")
                    maintenance_form.locator('button[type="submit"]').click()
                    request_id = handoff_page.evaluate("""async () => {
                        const {ERP_KEY} = await import('./engine.mjs');
                        const pm = JSON.parse(localStorage.getItem(ERP_KEY)).pm;
                        return pm.requests.find(r => r.machineId === 'DEMO-M-001' &&
                            r.status === 'OPEN')?.id || null;
                    }""")
                    assert request_id, "Synthetic maintenance request was not recorded"
                    handoff_page.evaluate("location.hash='#routing'")
                    handoff_page.locator('form[data-form="routing-capacity-review"]').wait_for(state="visible")
                    assert handoff_page.locator("#routing-capacity-result").count() == 0
                    assert handoff_page.locator('[data-action="routing-use-capacity-draft"]').count() == 0
                    assert stored_routing()["routing"] == before_request["routing"]
                    review_eligible_handoff(expect_eligible=False)
                    assert stored_routing()["routing"] == before_request["routing"], (
                        "Maintenance concerns must not silently change saved routing"
                    )
                    handoff_page.evaluate("location.hash='#pm'")
                    close_request = handoff_page.locator(
                        f'[data-action="pm-close-request"][data-id="{request_id}"]'
                    )
                    close_request.wait_for(state="visible")
                    close_request.click()
                    assert handoff_page.evaluate("""async (requestId) => {
                        const {ERP_KEY} = await import('./engine.mjs');
                        const pm = JSON.parse(localStorage.getItem(ERP_KEY)).pm;
                        return pm.requests.find(r => r.id === requestId)?.status === 'CLOSED';
                    }""", request_id)
                    handoff_page.evaluate("location.hash='#routing'")
                    handoff_page.locator('form[data-form="routing-capacity-review"]').wait_for(state="visible")
                    assert handoff_page.locator('[data-action="routing-use-capacity-draft"]').count() == 0
                    assert stored_routing()["routing"] == before_request["routing"]
                    review_eligible_handoff()

                    # A new fictional quality hold invalidates a previously
                    # eligible review before its suggestion can reach the editor.
                    before_hold = stored_routing()
                    handoff_page.evaluate("location.hash='#quality'")
                    quality_form = handoff_page.locator('form[data-form="new-ncr"]')
                    quality_form.wait_for(state="visible")
                    quality_form.locator('button[type="submit"]').click()
                    hold_id = handoff_page.evaluate("""async () => {
                        const {ERP_KEY} = await import('./engine.mjs');
                        const state = JSON.parse(localStorage.getItem(ERP_KEY));
                        return state.quality.filter(q => q.jobId === state.jobs[0].id &&
                            q.status === 'OPEN').at(-1)?.id || null;
                    }""")
                    assert hold_id, "Synthetic quality hold was not recorded"
                    assert stored_routing()["routing"] == before_hold["routing"]
                    handoff_page.evaluate("location.hash='#routing'")
                    handoff_page.locator('form[data-form="routing-capacity-review"]').wait_for(state="visible")
                    assert handoff_page.locator("#routing-capacity-result").count() == 0
                    assert handoff_page.locator('[data-action="routing-use-capacity-draft"]').count() == 0
                    assert handoff_page.locator("#routing-editor-form").count() == 0
                    assert stored_routing()["routing"] == before_hold["routing"], (
                        "A quality hold must not mutate the saved routing"
                    )
                    # Close the fictional hold through the real UI, then prove
                    # a fresh review is needed before an explicit draft save.
                    handoff_page.evaluate("location.hash='#quality'")
                    close_hold = handoff_page.locator(
                        f'[data-action="close-ncr"][data-id="{hold_id}"]'
                    )
                    close_hold.wait_for(state="visible")
                    close_hold.click()
                    handoff_page.evaluate("location.hash='#routing'")
                    handoff_page.locator('form[data-form="routing-capacity-review"]').wait_for(state="visible")
                    assert handoff_page.locator('[data-action="routing-use-capacity-draft"]').count() == 0
                    original = stored_routing()  # Quality events are legitimate; routing is unchanged.
                    assert original["routing"] == before_hold["routing"]

                    review_eligible_handoff()
                    handoff_page.locator('[data-action="routing-use-capacity-draft"]').click()
                    editor = handoff_page.locator("#routing-editor-form")
                    editor.locator('input[name="name-0"]').fill("Synthetic alternate cut review")
                    assert stored_routing()["raw"] == original["raw"]
                    handoff_page.locator('button[form="routing-editor-form"]').click()
                    saved = stored_routing()
                    assert saved["routing"]["operations"][0]["center"] == "DEMO-CUT"
                    assert saved["routing"]["operations"][0]["name"] == "Synthetic alternate cut review"
                    assert saved["routing"]["operations"][1:] == original["routing"]["operations"][1:]
                    assert saved["routing"]["reviewState"] == "REVIEW_REQUIRED"
                    assert saved["routing"]["source"] == "BROWSER-LOCAL ROUTING DRAFT"
                    assert saved["routing"]["history"][-1]["kind"] == "DRAFT_EDIT"
                    assert saved["events"] == original["events"] + ["routing.draft_edited"]
                    assert handoff_page.locator("#routing-editor-form").count() == 0
                    handoff_page.reload(wait_until="domcontentloaded")
                    assert stored_routing()["routing"]["operations"][0]["center"] == "DEMO-CUT"
                    assert "REVIEW_REQUIRED" in handoff_page.locator("#view").inner_text()
                finally:
                    handoff_context.close()

                # Separate fictional browser storage verifies a genuine clock
                # session blocks an otherwise eligible review-only handoff.
                # The original save/cancel journey remains untouched.
                clock_context = browser.new_context()
                try:
                    clock_page = clock_context.new_page()
                    clock_page.goto(url, wait_until="domcontentloaded")
                    completion = clock_page.locator('form[data-form="pm-complete"]')
                    completion.wait_for(state="visible")
                    completion.locator('select[name="task"]').select_option("DEMO-PM-001")
                    completion.locator('input[name="confirmed"]').check()
                    completion.locator('button[type="submit"]').click()
                    pm_link = clock_page.locator(FORM)
                    pm_link.locator('select[name="center"]').select_option("DEMO-CUT")
                    pm_link.locator('input[name="source"]').fill("SYN-CLOCK-PM-001")
                    pm_link.locator('input[name="confirmed"]').check()
                    pm_link.locator('button[type="submit"]').click()
                    clock_page.evaluate("location.hash='#routing'")
                    clock_page.locator('form[data-form="routing-capacity-review"]').wait_for(state="visible")
                    review_eligible_handoff(target_page=clock_page)
                    assert clock_page.locator('[data-action="routing-use-capacity-draft"]').count() == 1
                    canonical_before_clock = clock_page.evaluate("""async () => {
                        const {ERP_KEY} = await import('./engine.mjs');
                        return localStorage.getItem(ERP_KEY);
                    }""")
                    clock_page.evaluate("location.hash='#ewi'")
                    clock_page.locator('[data-action="clock-in"]').wait_for(state="visible")
                    clock_page.locator('[data-action="clock-in"]').click()
                    assert clock_page.evaluate("""async () => {
                        const {CLOCK_KEY,ERP_KEY} = await import('./engine.mjs');
                        const state = JSON.parse(localStorage.getItem(ERP_KEY));
                        const sessions = JSON.parse(localStorage.getItem(CLOCK_KEY));
                        return sessions.length === 1 &&
                            sessions[0].jobId === state.jobs[0].id && !sessions[0].end;
                    }"""), "Clock IN must create a genuine browser-local same-job session"
                    clock_page.evaluate("location.hash='#routing'")
                    clock_page.locator('form[data-form="routing-capacity-review"]').wait_for(state="visible")
                    assert clock_page.locator("#routing-capacity-result").count() == 0
                    assert clock_page.locator('[data-action="routing-use-capacity-draft"]').count() == 0
                    assert clock_page.locator("#routing-editor-form").count() == 0
                    review_eligible_handoff(
                        expect_eligible=False, target_page=clock_page,
                        expected_blocker="browser-local EWI clock history",
                    )
                    assert "Browser-local EWI clock sessions on this job: 1" in (
                        clock_page.locator("#routing-capacity-result").inner_text()
                    )
                    assert clock_page.locator('[data-action="routing-use-capacity-draft"]').count() == 0
                    assert clock_page.evaluate("""async () => {
                        const {ERP_KEY} = await import('./engine.mjs');
                        return localStorage.getItem(ERP_KEY);
                    }""") == canonical_before_clock, (
                        "Clocking and rejected suggestions must not change canonical ERP routing"
                    )
                    clock_page.evaluate("location.hash='#ewi'")
                    clock_page.locator('[data-action="clock-out"]').click()
                    clock_page.evaluate("location.hash='#routing'")
                    clock_page.locator('form[data-form="routing-capacity-review"]').wait_for(state="visible")
                    assert clock_page.locator("#routing-capacity-result").count() == 0
                    review_eligible_handoff(
                        expect_eligible=False, target_page=clock_page,
                        expected_blocker="browser-local EWI clock history",
                    )
                    assert clock_page.evaluate("""async () => {
                        const {CLOCK_KEY} = await import('./engine.mjs');
                        const sessions = JSON.parse(localStorage.getItem(CLOCK_KEY));
                        return sessions.length === 1 && Boolean(sessions[0].end);
                    }"""), "A stopped clock remains historical evidence"
                    assert clock_page.locator('[data-action="routing-use-capacity-draft"]').count() == 0
                    assert clock_page.evaluate("""async () => {
                        const {ERP_KEY} = await import('./engine.mjs');
                        return localStorage.getItem(ERP_KEY);
                    }""") == canonical_before_clock
                finally:
                    clock_context.close()

                context.close()
                print("PASS: Chromium PM lifecycle, capacity review, and explicit routing handoff cancel/save")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    browser_test()
