"""Browser-level regression for the fictional Quality Forge evidence round trip.

Run from the repository after installing Playwright and its Chromium browser:
    python web/erp/quality-navigation.browser.py
No external service, real records, or browser storage is used.
"""
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import expect, sync_playwright


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    web_root = Path(__file__).resolve().parents[1]
    handler = partial(QuietHandler, directory=str(web_root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                page = browser.new_page()
                page_errors = []
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/erp/#quality")
                expect(page.locator('form[data-form="new-ncr"]')).to_be_visible()
                job_id = page.locator("#job-context").input_value()
                assert job_id, "A fictional work order must be selected"

                page.locator('form[data-form="new-ncr"] button[type="submit"]').click()
                panel = page.locator("#quality-case-detail")
                case_id = panel.get_attribute("data-case-id")
                assert case_id, "Creating a synthetic NCR must select its case"

                page.locator('form[data-form="quality-inspection"] textarea[name="observation"]').fill(
                    "Synthetic first-piece inspection observation"
                )
                inspection_step = page.locator('form[data-form="quality-inspection"] select[name="step"]').input_value()
                page.locator('form[data-form="quality-inspection"] button[type="submit"]').click()
                inspection_id = panel.locator('[data-evidence-kind="inspection"]').first.get_attribute("data-evidence-id")
                assert inspection_id

                # Both the observation receipt and case chronology must open
                # the SAME existing corrective form with exact inspection context.
                handoffs = panel.locator(
                    f'button[data-action="quality-inspection-corrective"][data-case="{case_id}"][data-id="{inspection_id}"]'
                )
                assert handoffs.count() == 2, "Receipt and chronology should offer one canonical action draft"
                corrective_picker = page.locator('form[data-form="quality-corrective-action"] select[name="inspectionId"]')
                corrective_note = page.locator('form[data-form="quality-corrective-action"] textarea[name="description"]')
                for handoff in (handoffs.first, handoffs.last):
                    corrective_picker.select_option("")
                    handoff.click()
                    expect(corrective_picker).to_have_value(inspection_id)
                    assert corrective_note.evaluate("el => document.activeElement === el")
                    assert panel.get_attribute("data-case-id") == case_id
                    expect(page.locator("#job-context")).to_have_value(job_id)
                assert panel.locator('[data-evidence-kind="corrective"]').count() == 0, (
                    "Selecting a handoff must not create an action before submission"
                )
                page.locator('form[data-form="quality-corrective-action"] select[name="inspectionId"]').select_option(index=1)
                page.locator('form[data-form="quality-corrective-action"] textarea[name="description"]').fill(
                    "Synthetic corrective action tied to inspection"
                )
                page.locator('form[data-form="quality-corrective-action"] button[type="submit"]').click()
                corrective_id = panel.locator('[data-evidence-kind="corrective"]').first.get_attribute("data-evidence-id")
                assert corrective_id

                page.locator('form[data-form="quality-disposition"] select[name="decision"]').select_option("SCRAP")
                page.locator('form[data-form="quality-disposition"] textarea[name="note"]').fill(
                    "Synthetic disposition recorded for review"
                )
                page.locator('form[data-form="quality-disposition"] button[type="submit"]').click()
                page.locator('form[data-form="quality-reviewed-close"] button[type="submit"]').click()
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")
                assert panel.locator('button[data-action="quality-inspection-corrective"]').count() == 0, (
                    "Closed fictional cases cannot start new corrective actions"
                )

                # The current canonical disposition is reachable from its chronology
                # and retains its original NCR identity after closure.
                disposition_receipt = panel.locator(
                    f'[data-evidence-kind="disposition"][data-evidence-id="{case_id}"]'
                )
                expect(disposition_receipt).to_have_count(1)
                panel.locator(
                    f'button[data-action="quality-evidence-focus"][data-kind="disposition"][data-id="{case_id}"]'
                ).click()
                assert disposition_receipt.evaluate("el => document.activeElement === el")

                # The inspection receipt and its chronology independently
                # locate the same corrective evidence without changing state.
                inspection_receipt_action = panel.locator(
                    f'[data-evidence-kind="inspection"][data-evidence-id="{inspection_id}"] '
                    f'button[data-action="quality-evidence-focus"][data-kind="corrective"][data-id="{corrective_id}"]'
                )
                inspection_chronology_action = panel.locator(
                    'h3:has-text("Case chronology") ~ div.receipt'
                ).filter(has_text="Inspection:").locator(
                    f'button[data-action="quality-evidence-focus"][data-kind="corrective"][data-id="{corrective_id}"]'
                )
                expect(inspection_receipt_action).to_have_count(1)
                expect(inspection_chronology_action).to_have_count(1)
                for action_link in (inspection_receipt_action, inspection_chronology_action):
                    action_link.click()
                    corrective_evidence = panel.locator(
                        f'[data-evidence-kind="corrective"][data-evidence-id="{corrective_id}"]'
                    ).first
                    assert corrective_evidence.evaluate("el => document.activeElement === el")
                    assert panel.get_attribute("data-case-id") == case_id
                    expect(page.locator("#job-context")).to_have_value(job_id)
                    expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                # Corrective receipt and chronology return to the exact
                # source inspection without writing or reopening the case.
                corrective_receipt_source = panel.locator(
                    f'[data-evidence-kind="corrective"][data-evidence-id="{corrective_id}"] > '
                    f'button[data-action="quality-evidence-focus"][data-kind="inspection"][data-id="{inspection_id}"]'
                )
                corrective_chronology_source = panel.locator(
                    'h3:has-text("Case chronology") ~ div.receipt'
                ).filter(has_text="Corrective action:").locator(
                    f'button[data-action="quality-evidence-focus"][data-kind="inspection"][data-id="{inspection_id}"]'
                )
                expect(corrective_receipt_source).to_have_count(1)
                expect(corrective_chronology_source).to_have_count(1)
                for source in (corrective_receipt_source, corrective_chronology_source):
                    source.click()
                    observation = panel.locator(
                        f'[data-evidence-kind="inspection"][data-evidence-id="{inspection_id}"]'
                    ).first
                    assert observation.evaluate("el => document.activeElement === el")
                    expect(page.locator("#job-context")).to_have_value(job_id)
                    expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                # The corrective receipt and case chronology must reach the
                # SAME existing review form after closure without writing evidence.
                review_handoffs = panel.locator(
                    f'button[data-action="quality-corrective-review"][data-case="{case_id}"][data-id="{corrective_id}"]'
                )
                assert review_handoffs.count() == 2, "Both entry points should target one corrective action"
                review_note = page.locator('form[data-form="quality-effectiveness"] textarea[name="note"]')
                for handoff in (review_handoffs.first, review_handoffs.last):
                    handoff.click()
                    assert review_note.evaluate("el => document.activeElement === el")
                    assert panel.get_attribute("data-case-id") == case_id
                    expect(page.locator("#job-context")).to_have_value(job_id)
                    assert panel.locator('[data-evidence-kind="effectiveness"]').count() == 0, (
                        "Review navigation must not create evidence before submission"
                    )

                page.locator('form[data-form="quality-effectiveness"] textarea[name="note"]').fill(
                    "Synthetic post-closure effectiveness review"
                )
                page.locator('form[data-form="quality-effectiveness"] button[type="submit"]').click()
                review_id = panel.locator('[data-evidence-kind="effectiveness"]').first.get_attribute("data-evidence-id")
                assert review_id
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                # From either the chronology or the review receipt, navigate to
                # the exact corrective action without changing case or job.
                parent = panel.locator(
                    f'[data-evidence-kind="corrective"][data-evidence-id="{corrective_id}"]'
                )
                parent_links = panel.locator(
                    f'button[data-action="quality-evidence-focus"][data-kind="corrective"][data-id="{corrective_id}"]'
                )
                assert parent_links.count() >= 2, "Review and chronology must expose parent action"
                parent_links.last.click()
                assert parent.evaluate("el => document.activeElement === el")
                panel.locator(
                    f'[data-evidence-kind="effectiveness"][data-evidence-id="{review_id}"] '
                    'button[data-action="quality-evidence-focus"][data-kind="corrective"]'
                ).click()
                assert parent.evaluate("el => document.activeElement === el")
                panel.locator(
                    f'button[data-action="quality-evidence-focus"][data-kind="effectiveness"][data-id="{review_id}"]'
                ).click()
                review_receipt = panel.locator(
                    f'[data-evidence-kind="effectiveness"][data-evidence-id="{review_id}"]'
                )
                assert review_receipt.evaluate("el => document.activeElement === el")
                assert panel.get_attribute("data-case-id") == case_id
                expect(page.locator("#job-context")).to_have_value(job_id)

                # The effectiveness receipt and its chronology entry both
                # return to the exact inspection cited by the parent action.
                receipt_source = panel.locator(
                    f'[data-evidence-kind="effectiveness"][data-evidence-id="{review_id}"] '
                    f'button[data-action="quality-evidence-focus"][data-kind="inspection"][data-id="{inspection_id}"]'
                )
                chronology_source = panel.locator(
                    'h3:has-text("Case chronology") ~ div.receipt'
                ).filter(has_text="Effectiveness:").locator(
                    f'button[data-action="quality-evidence-focus"][data-kind="inspection"][data-id="{inspection_id}"]'
                )
                expect(receipt_source).to_have_count(1)
                expect(chronology_source).to_have_count(1)
                for source in (receipt_source, chronology_source):
                    source.click()
                    observation = panel.locator(
                        f'[data-evidence-kind="inspection"][data-evidence-id="{inspection_id}"]'
                    ).first
                    assert observation.evaluate("el => document.activeElement === el")
                    assert panel.get_attribute("data-case-id") == case_id
                    expect(page.locator("#job-context")).to_have_value(job_id)
                    expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                # Follow-up evidence is recorded on the same closed NCR, then
                # reached from its chronology without creating another case.
                page.locator('form[data-form="quality-followup"] textarea[name="note"]').fill(
                    "Synthetic post-closure case follow-up"
                )
                page.locator('form[data-form="quality-followup"] button[type="submit"]').click()
                followup_id = panel.locator('[data-evidence-kind="followup"]').first.get_attribute("data-evidence-id")
                assert followup_id
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")
                panel.locator(
                    f'button[data-action="quality-evidence-focus"][data-kind="followup"][data-id="{followup_id}"]'
                ).click()
                followup_receipt = panel.locator(
                    f'[data-evidence-kind="followup"][data-evidence-id="{followup_id}"]'
                ).first
                assert followup_receipt.evaluate("el => document.activeElement === el")

                for kind, evidence_id in (
                    ("inspection", inspection_id),
                    ("disposition", case_id),
                    ("corrective", corrective_id),
                    ("effectiveness", review_id),
                    ("followup", followup_id),
                ):
                    panel.locator(
                        f'button[data-action="quality-evidence-work-order"][data-kind="{kind}"][data-id="{evidence_id}"]'
                    ).click()
                    page.wait_for_function("location.hash === '#jobs'")
                    expect(page.locator("#job-context")).to_have_value(job_id)
                    return_button = page.locator('button[data-action="quality-evidence-return"]')
                    expect(return_button).to_have_count(1)
                    assert return_button.get_attribute("data-case") == case_id
                    assert return_button.get_attribute("data-kind") == kind
                    assert return_button.get_attribute("data-id") == evidence_id

                    if kind in ("inspection", "disposition", "followup"):
                        other_job = page.locator("#job-context option").evaluate_all(
                            "(options, selected) => options.map(o => o.value).find(v => v !== selected)", job_id
                        )
                        assert other_job, "Synthetic seed must have another job for guard coverage"
                        page.locator("#job-context").select_option(other_job)
                        expect(return_button).to_have_count(0)
                        page.locator("#job-context").select_option(job_id)
                        expect(return_button).to_have_count(1)

                    return_button.click()
                    page.wait_for_function("location.hash === '#quality'")
                    assert panel.get_attribute("data-case-id") == case_id
                    evidence = panel.locator(
                        f'[data-evidence-kind="{kind}"][data-evidence-id="{evidence_id}"]'
                    ).first
                    expect(evidence).to_be_visible()
                    assert evidence.evaluate("el => document.activeElement === el"), (
                        f"Return must focus original {kind} evidence"
                    )
                    expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                # Routing is a separate job-first entry point to the exact
                # historical inspection. It must not substitute a different job.
                page.locator('#module-nav a[data-nav="routing"]').click()
                page.wait_for_function("location.hash === '#routing'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                job_inspection_link = page.locator(
                    f'button[data-action="job-quality-inspection"][data-case="{case_id}"]'
                    f'[data-job="{job_id}"][data-id="{inspection_id}"]'
                )
                expect(job_inspection_link).to_have_count(1)
                other_routing_job = page.locator("#job-context option").evaluate_all(
                    "(options, selected) => options.map(o => o.value).find(v => v !== selected)", job_id
                )
                assert other_routing_job
                page.locator("#job-context").select_option(other_routing_job)
                expect(page.locator('button[data-action="job-quality-inspection"]')).to_have_count(0)
                page.locator("#job-context").select_option(job_id)
                expect(job_inspection_link).to_have_count(1)
                job_inspection_link.click()
                page.wait_for_function("location.hash === '#quality'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(panel).to_have_attribute("data-case-id", case_id)
                focused_observation = panel.locator(
                    f'[data-evidence-kind="inspection"][data-evidence-id="{inspection_id}"]'
                ).first
                assert focused_observation.evaluate("el => document.activeElement === el")
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                editable = page.locator('form[data-form="quality-followup"] textarea')
                native_menu = editable.evaluate("""el => {
                    const event = new MouseEvent('contextmenu', {bubbles: true, cancelable: true, button: 2});
                    el.dispatchEvent(event);
                    return !event.defaultPrevented;
                }""")
                assert native_menu, "Native context menu must remain available in editable fields"

                # A job's dashboard NCR badge must open its canonical case, even
                # when the global job selector currently points to another job.
                page.locator('#module-nav a[data-nav="dashboard"]').click()
                page.wait_for_function("location.hash === '#dashboard'")
                other_job = page.locator("#job-context option").evaluate_all(
                    "(options, selected) => options.map(o => o.value).find(v => v !== selected)", job_id
                )
                assert other_job, "Synthetic seed must have another work order"
                page.locator("#job-context").select_option(other_job)
                dashboard_badge = page.locator(
                    f'button[data-action="job-quality-cases"][data-id="{job_id}"]'
                )
                expect(dashboard_badge).to_have_count(1)
                dashboard_badge.click()
                page.wait_for_function("location.hash === '#quality'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(panel).to_have_attribute("data-case-id", case_id)
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")
                expect(
                    panel.locator(
                        f'[data-evidence-kind="inspection"][data-evidence-id="{inspection_id}"]'
                    ).first
                ).to_be_visible()

                # Search is an independent entry point into the same working
                # Quality Control screen, not a second copy of the NCR data.
                page.locator('#module-nav a[data-nav="jobs"]').click()
                page.wait_for_function("location.hash === '#jobs'")
                search = page.locator("#menu-search")
                search.fill("effectiveness review")
                expect(page.locator('#module-nav a[data-nav="quality"]')).to_be_visible()
                search.press("Enter")
                page.wait_for_function("location.hash === '#quality'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(panel).to_have_attribute("data-case-id", case_id)
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")
                expect(
                    panel.locator(
                        f'[data-evidence-kind="effectiveness"][data-evidence-id="{review_id}"]'
                    ).first
                ).to_be_visible()
                assert search.input_value() == "", "Successful search navigation should clear its query"

                # Report Center is a third independent path to the same
                # fictional NCR, including its post-closure evidence.
                report_search = page.locator("#menu-search")
                report_search.fill("report center")
                expect(page.locator('#module-nav a[data-nav="reports"]')).to_be_visible()
                report_search.press("Enter")
                page.wait_for_function("location.hash === '#reports'")
                page.locator("#report-select").select_option("quality")
                report_case = page.locator(
                    f'button[data-action="report-quality-case"][data-id="{case_id}"]'
                )
                expect(report_case).to_have_count(1)
                expect(report_case).to_be_visible()
                page.locator("#job-context").select_option(other_job)
                report_case.click()
                page.wait_for_function("location.hash === '#quality'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(panel).to_have_attribute("data-case-id", case_id)
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")
                expect(panel.locator(
                    f'[data-evidence-kind="effectiveness"][data-evidence-id="{review_id}"]'
                ).first).to_be_visible()

                # The report entry must also support the existing evidence
                # to work-order to exact-evidence round trip.
                panel.locator(
                    f'button[data-action="quality-evidence-work-order"][data-kind="effectiveness"][data-id="{review_id}"]'
                ).click()
                page.wait_for_function("location.hash === '#jobs'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                report_return = page.locator('button[data-action="quality-evidence-return"]')
                expect(report_return).to_have_count(1)
                assert report_return.get_attribute("data-case") == case_id
                assert report_return.get_attribute("data-kind") == "effectiveness"
                assert report_return.get_attribute("data-id") == review_id
                report_return.click()
                page.wait_for_function("location.hash === '#quality'")
                review_evidence = panel.locator(
                    f'[data-evidence-kind="effectiveness"][data-evidence-id="{review_id}"]'
                ).first
                expect(review_evidence).to_be_visible()
                assert review_evidence.evaluate("el => document.activeElement === el")
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                # The case's own related-workflow links must restore its job
                # from a different global selection, without changing NCR
                # identity or creating a second quality record.
                for target_view in ("jobs", "routing", "documents", "ewi"):
                    page.locator("#job-context").select_option(other_job)
                    expect(panel).to_have_attribute("data-case-id", case_id)
                    case_link = panel.locator(f'a[href="#{target_view}"][data-job="{job_id}"]')
                    expect(case_link).to_have_count(1)
                    native_case_link = case_link.evaluate("""el => {
                        const event = new MouseEvent('contextmenu',
                            {bubbles: true, cancelable: true, button: 2});
                        el.dispatchEvent(event);
                        return !event.defaultPrevented;
                    }""")
                    assert native_case_link, "Case links must retain native browser right-click"
                    case_link.click()
                    page.wait_for_function("(view) => location.hash === '#' + view", arg=target_view)
                    expect(page.locator("#job-context")).to_have_value(job_id)
                    page.locator('#module-nav a[data-nav="quality"]').click()
                    page.wait_for_function("location.hash === '#quality'")
                    expect(panel).to_have_attribute("data-case-id", case_id)
                    expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")
                    expect(panel.locator(
                        f'[data-evidence-kind="effectiveness"][data-evidence-id="{review_id}"]'
                    ).first).to_be_visible()
                assert page.locator('#view [data-action="select-quality"][data-id="' + case_id + '"]').count() == 1, (
                    "Related-workflow links must not duplicate the canonical NCR"
                )

                # The NCR heading is an accessible record-specific Open with
                # entry point. It reuses the canonical quality context menu,
                # not a second navigation or quality record implementation.
                case_heading = panel.locator('h2.context-record[data-ctx-type="quality"]')
                expect(case_heading).to_have_attribute("data-ctx-id", case_id)
                page.locator("#job-context").select_option(other_job)
                case_heading.focus()
                case_heading.press("Shift+F10")
                case_menu = page.locator("#axiom-record-menu")
                expect(case_menu).to_be_visible()
                case_number = case_heading.inner_text().split(" · ", 1)[-1]
                expect(case_menu.locator(".record-menu-heading")).to_have_text(case_number)
                expect(case_menu.get_by_role("menuitem", name="Job Tracker")).to_be_visible()
                page.keyboard.press("Escape")
                expect(case_menu).to_be_hidden()
                assert case_heading.evaluate("el => document.activeElement === el"), (
                    "Escape must restore focus to the original NCR heading"
                )
                native_case_heading = case_heading.evaluate("""el => {
                    const event = new MouseEvent('contextmenu',
                        {bubbles: true, cancelable: true, button: 2, shiftKey: true});
                    el.dispatchEvent(event);
                    return !event.defaultPrevented;
                }""")
                assert native_case_heading, "Shift+right-click must retain the browser menu"
                case_heading.press("ContextMenu")
                expect(case_menu).to_be_visible()
                case_menu.get_by_role("menuitem", name="Job Tracker").click()
                page.wait_for_function("location.hash === '#jobs'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(page.locator(".context-trail")).to_contain_text(case_number)
                page.locator('#module-nav a[data-nav="quality"]').click()
                page.wait_for_function("location.hash === '#quality'")
                expect(panel).to_have_attribute("data-case-id", case_id)
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")
                expect(panel.locator(
                    f'[data-evidence-kind="effectiveness"][data-evidence-id="{review_id}"]'
                ).first).to_be_visible()
                expect(page.locator(
                    f'#view button[data-action="select-quality"][data-id="{case_id}"]'
                )).to_have_count(1)

                # An inspection's routed-step action must resolve the exact
                # current operation, even when another job was selected.
                route_action = panel.locator(
                    f'button[data-action="quality-routing-step"][data-id="{inspection_id}"]'
                )
                expect(route_action.first).to_be_visible()
                page.locator("#job-context").select_option(other_job)
                route_action.first.click()
                page.wait_for_function("location.hash === '#routing'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                route_card = page.locator("#view [data-route-step]:focus")
                expect(route_card).to_have_count(1)
                routed_step = route_card.get_attribute("data-route-step")
                assert routed_step == inspection_step, "Routing jump must focus the recorded operation"
                page.locator('#module-nav a[data-nav="quality"]').click()
                page.wait_for_function("location.hash === '#quality'")
                expect(panel).to_have_attribute("data-case-id", case_id)
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                # A simulated drawing revision change makes the historical
                # inspection ineligible for a CURRENT routing-step jump.
                # The evidence and work-order link must remain available.
                page.locator('#module-nav a[data-nav="documents"]').click()
                page.wait_for_function("location.hash === '#documents'")
                revision_select = page.locator('form[data-form="drawing-rev"] select[name="revision"]')
                original_revision = revision_select.input_value()
                other_revision = revision_select.locator("option").evaluate_all(
                    "(options, current) => options.map(o => o.value).find(v => v !== current)",
                    original_revision,
                )
                assert other_revision, "Fictional drawing needs an alternate revision"
                revision_select.select_option(other_revision)
                page.locator('form[data-form="drawing-rev"] button[type="submit"]').click()
                page.locator('#module-nav a[data-nav="quality"]').click()
                page.wait_for_function("location.hash === '#quality'")
                expect(panel).to_have_attribute("data-case-id", case_id)
                expect(route_action).to_have_count(0)
                expect(panel.locator('[role="note"]').filter(
                    has_text="Recorded drawing revision differs"
                ).first).to_be_visible()
                expect(panel.locator(
                    f'button[data-action="quality-evidence-work-order"][data-kind="inspection"][data-id="{inspection_id}"]'
                ).first).to_be_visible()
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                # Restoring the fictional drawing revision restores only the
                # valid navigation action; it never reopens the closed NCR.
                page.locator('#module-nav a[data-nav="documents"]').click()
                page.wait_for_function("location.hash === '#documents'")
                page.locator('form[data-form="drawing-rev"] select[name="revision"]').select_option(
                    original_revision
                )
                page.locator('form[data-form="drawing-rev"] button[type="submit"]').click()
                page.locator('#module-nav a[data-nav="quality"]').click()
                page.wait_for_function("location.hash === '#quality'")
                expect(route_action.first).to_be_visible()
                expect(panel).to_have_attribute("data-case-id", case_id)
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                # The canonical work-order register is another independent
                # entry point to the exact closed-case inspection. The global
                # job selection may point at a different fictional work order.
                page.locator('#module-nav a[data-nav="jobs"]').click()
                page.wait_for_function("location.hash === '#jobs'")
                clear_context = page.locator('#view button[data-action="clear-record-context"]')
                if clear_context.count():
                    clear_context.click()
                page.locator("#job-context").select_option(other_job)
                target_row = page.locator("#view table tbody tr").filter(
                    has=page.locator(f'a.cell-link[data-job="{job_id}"]')
                )
                expect(target_row).to_have_count(1)
                details = target_row.locator("details.job-inspection-details")
                expect(details).to_have_count(1)
                expect(details.locator("summary")).to_have_text("Quality evidence (5)")
                unrelated_row = page.locator("#view table tbody tr").filter(
                    has=page.locator(f'a.cell-link[data-job="{other_job}"]')
                )
                expect(unrelated_row.locator("details.job-inspection-details")).to_have_count(0)
                details.locator("summary").click()
                register_jump = details.locator(
                    f'button[data-action="job-quality-inspection"][data-case="{case_id}"]'
                    f'[data-job="{job_id}"][data-id="{inspection_id}"]'
                )
                expect(register_jump).to_be_visible()
                expect(page.locator("#job-context")).to_have_value(other_job)
                register_jump.click()
                page.wait_for_function("location.hash === '#quality'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(panel).to_have_attribute("data-case-id", case_id)
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")
                register_inspection = panel.locator(
                    f'[data-evidence-kind="inspection"][data-evidence-id="{inspection_id}"]'
                ).first
                expect(register_inspection).to_be_visible()
                assert register_inspection.evaluate("el => document.activeElement === el"), (
                    "Register jump must focus the exact canonical inspection"
                )
                expect(page.locator(
                    f'#view button[data-action="select-quality"][data-id="{case_id}"]'
                )).to_have_count(1)

                # Corrective evidence is reachable from routing and the job
                # register, with the same case, action and job identity.
                page.locator('#module-nav a[data-nav="routing"]').click()
                page.wait_for_function("location.hash === '#routing'")
                routed_corrective = page.locator(
                    f'#view button[data-action="job-quality-corrective"][data-case="{case_id}"]'
                    f'[data-job="{job_id}"][data-id="{corrective_id}"]'
                )
                expect(routed_corrective).to_have_count(1)
                routed_corrective.click()
                page.wait_for_function("location.hash === '#quality'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(panel).to_have_attribute("data-case-id", case_id)
                corrective_receipt = panel.locator(
                    f'[data-evidence-kind="corrective"][data-evidence-id="{corrective_id}"]'
                ).first
                assert corrective_receipt.evaluate("el => document.activeElement === el"), (
                    "Routing jump must focus the exact corrective evidence"
                )
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                page.locator('#module-nav a[data-nav="jobs"]').click()
                page.wait_for_function("location.hash === '#jobs'")
                expect(page.locator("#view h2").filter(has_text="Shop order register")).to_be_visible()
                clear_context = page.locator('#view button[data-action="clear-record-context"]')
                if clear_context.count():
                    clear_context.click()
                page.locator("#job-context").select_option(other_job)
                target_row = page.locator("#view table tbody tr").filter(
                    has=page.locator(f'a.cell-link[data-job="{job_id}"]')
                )
                details = target_row.locator("details.job-inspection-details")
                expect(details.locator("summary")).to_have_text("Quality evidence (5)")
                details.locator("summary").click()
                register_corrective = details.locator(
                    f'button[data-action="job-quality-corrective"][data-case="{case_id}"]'
                    f'[data-job="{job_id}"][data-id="{corrective_id}"]'
                )
                expect(register_corrective).to_be_visible()
                expect(page.locator("#job-context")).to_have_value(other_job)
                register_corrective.click()
                page.wait_for_function("location.hash === '#quality'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(panel).to_have_attribute("data-case-id", case_id)
                assert corrective_receipt.evaluate("el => document.activeElement === el"), (
                    "Register jump must focus the same canonical corrective action"
                )
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")


                # Post-closure follow-up evidence uses the same canonical NCR
                # from both work-order entry points without changing records.
                page.locator('#module-nav a[data-nav="routing"]').click()
                page.wait_for_function("location.hash === '#routing'")
                routing_followup = page.locator(
                    f'#view button[data-action="job-quality-followup"][data-case="{case_id}"]'
                    f'[data-job="{job_id}"][data-id="{followup_id}"]'
                )
                expect(routing_followup).to_have_count(1)
                routing_followup.click()
                page.wait_for_function("location.hash === '#quality'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(panel).to_have_attribute("data-case-id", case_id)
                assert followup_receipt.evaluate("el => document.activeElement === el")
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                page.locator('#module-nav a[data-nav="jobs"]').click()
                page.wait_for_function("location.hash === '#jobs'")
                expect(page.locator("#view h2").filter(has_text="Shop order register")).to_be_visible()
                clear_context = page.locator('#view button[data-action="clear-record-context"]')
                if clear_context.count():
                    clear_context.first.evaluate("(el) => el.click()")
                page.locator("#job-context").select_option(other_job)
                target_row = page.locator("#view table tbody tr").filter(
                    has=page.locator(f'a.cell-link[data-job="{job_id}"]')
                )
                details = target_row.locator("details.job-inspection-details")
                expect(details.locator("summary")).to_have_text("Quality evidence (5)")
                details.locator("summary").click()
                register_followup = details.locator(
                    f'button[data-action="job-quality-followup"][data-case="{case_id}"]'
                    f'[data-job="{job_id}"][data-id="{followup_id}"]'
                )
                expect(register_followup).to_be_visible()
                expect(page.locator("#job-context")).to_have_value(other_job)
                register_followup.click()
                page.wait_for_function("location.hash === '#quality'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(panel).to_have_attribute("data-case-id", case_id)
                assert followup_receipt.evaluate("el => document.activeElement === el")
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                # Both work-order views reach the same recorded disposition.
                page.locator('#module-nav a[data-nav="routing"]').click()
                page.wait_for_function("location.hash === '#routing'")
                routing_disposition = page.locator(
                    f'#view button[data-action="job-quality-disposition"][data-case="{case_id}"]'
                    f'[data-job="{job_id}"][data-id="{case_id}"]'
                )
                expect(routing_disposition).to_have_count(1)
                routing_disposition.click()
                page.wait_for_function("location.hash === '#quality'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(panel).to_have_attribute("data-case-id", case_id)
                assert disposition_receipt.evaluate("el => document.activeElement === el")
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                page.locator('#module-nav a[data-nav="jobs"]').click()
                page.wait_for_function("location.hash === '#jobs'")
                expect(page.locator("#view h2").filter(has_text="Shop order register")).to_be_visible()
                page.evaluate("""() => {
                    document.querySelector('#view button[data-action="clear-record-context"]')?.click();
                }""")
                page.locator("#job-context").select_option(other_job)
                target_row = page.locator("#view table tbody tr").filter(
                    has=page.locator(f'a.cell-link[data-job="{job_id}"]')
                )
                details = target_row.locator("details.job-inspection-details")
                expect(details.locator("summary")).to_have_text("Quality evidence (5)")
                details.locator("summary").click()
                register_disposition = details.locator(
                    f'button[data-action="job-quality-disposition"][data-case="{case_id}"]'
                    f'[data-job="{job_id}"][data-id="{case_id}"]'
                )
                expect(register_disposition).to_be_visible()
                expect(page.locator("#job-context")).to_have_value(other_job)
                register_disposition.click()
                page.wait_for_function("location.hash === '#quality'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(panel).to_have_attribute("data-case-id", case_id)
                assert disposition_receipt.evaluate("el => document.activeElement === el")
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                # The same recorded review is reachable from routing and the
                # shop order register, even when another job is selected.
                page.locator('#module-nav a[data-nav="routing"]').click()
                page.wait_for_function("location.hash === '#routing'")
                routing_review = page.locator(
                    f'#view button[data-action="job-quality-effectiveness"][data-case="{case_id}"]'
                    f'[data-job="{job_id}"][data-id="{review_id}"]'
                )
                expect(routing_review).to_have_count(1)
                routing_review.click()
                page.wait_for_function("location.hash === '#quality'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(panel).to_have_attribute("data-case-id", case_id)
                review_receipt = panel.locator(
                    f'[data-evidence-kind="effectiveness"][data-evidence-id="{review_id}"]'
                ).first
                assert review_receipt.evaluate("el => document.activeElement === el")
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                page.locator('#module-nav a[data-nav="jobs"]').click()
                page.wait_for_function("location.hash === '#jobs'")
                page.evaluate("""() => {
                    document.querySelector('#view button[data-action="clear-record-context"]')?.click();
                }""")
                page.locator("#job-context").select_option(other_job)
                target_row = page.locator("#view table tbody tr").filter(
                    has=page.locator(f'a.cell-link[data-job="{job_id}"]')
                )
                details = target_row.locator("details.job-inspection-details")
                expect(details.locator("summary")).to_have_text("Quality evidence (5)")
                details.locator("summary").click()
                register_review = details.locator(
                    f'button[data-action="job-quality-effectiveness"][data-case="{case_id}"]'
                    f'[data-job="{job_id}"][data-id="{review_id}"]'
                )
                expect(register_review).to_be_visible()
                expect(page.locator("#job-context")).to_have_value(other_job)
                register_review.click()
                page.wait_for_function("location.hash === '#quality'")
                expect(page.locator("#job-context")).to_have_value(job_id)
                expect(panel).to_have_attribute("data-case-id", case_id)
                assert review_receipt.evaluate("el => document.activeElement === el")
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                # Existing inline part records provide a real Open with entry
                # point even while the separate record-row fix remains in #48.
                page.locator('#module-nav a[data-nav="jobs"]').click()
                page.wait_for_function("location.hash === '#jobs'")
                part_record = page.locator('#view .context-record[data-ctx-type="part"]').first
                expect(part_record).to_be_visible()
                part_number = part_record.get_attribute("data-ctx-id")
                assert part_number, "Part Open with requires a canonical fictional part"
                job_count = page.locator("#job-context option").count()
                record_menu = page.locator("#axiom-record-menu")

                # The app must not hijack native browser menus on links,
                # Shift+right-click, or selected text.
                native_link = page.locator("#view a.cell-link").first
                native_link_result = native_link.evaluate("""el => {
                    const event = new MouseEvent('contextmenu',
                        {bubbles: true, cancelable: true, button: 2});
                    el.dispatchEvent(event);
                    return !event.defaultPrevented;
                }""")
                assert native_link_result, "Links must retain native right-click"
                shifted_result = part_record.evaluate("""el => {
                    const event = new MouseEvent('contextmenu',
                        {bubbles: true, cancelable: true, button: 2, shiftKey: true});
                    el.dispatchEvent(event);
                    return !event.defaultPrevented;
                }""")
                assert shifted_result, "Shift+right-click must retain browser menu"
                selected_text_result = part_record.evaluate("""el => {
                    const selection = window.getSelection();
                    const range = document.createRange();
                    range.selectNodeContents(el);
                    selection.removeAllRanges();
                    selection.addRange(range);
                    const event = new MouseEvent('contextmenu',
                        {bubbles: true, cancelable: true, button: 2});
                    el.dispatchEvent(event);
                    const preserved = !event.defaultPrevented;
                    selection.removeAllRanges();
                    return preserved;
                }""")
                assert selected_text_result, "Selected text must retain native context menu"
                expect(record_menu).to_be_hidden()

                # Both keyboard paths open the same real part actions.
                part_record.focus()
                part_record.press("Shift+F10")
                expect(record_menu).to_be_visible()
                expect(record_menu.locator(".record-menu-heading")).to_have_text(part_number)
                entry_action = record_menu.get_by_role("menuitem", name="Job Entry (this part)")
                expect(entry_action).to_be_visible()
                page.keyboard.press("Escape")
                expect(record_menu).to_be_hidden()
                assert part_record.evaluate("el => document.activeElement === el"), (
                    "Escape should return focus to the originating part"
                )

                part_record.press("ContextMenu")
                expect(record_menu).to_be_visible()
                record_menu.get_by_role("menuitem", name="Job Entry (this part)").click()
                expect(record_menu).to_be_hidden()
                expect(page.locator('[data-form="new-job"] select[name="part"]')).to_have_value(part_number)
                expect(page.locator(".context-trail")).to_contain_text(part_number)
                assert page.locator("#job-context option").count() == job_count, (
                    "Opening Job Entry must not silently create a work order"
                )
                # Returning to Quality must show the original canonical case,
                # not create a second quality register.
                page.locator('#module-nav a[data-nav="quality"]').click()
                page.wait_for_function("location.hash === '#quality'")
                expect(panel).to_have_attribute("data-case-id", case_id)
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")
                # A legacy duplicate visible NCR number must still open each
                # distinct canonical case from its own Report Center row.
                duplicate_case_id = "q-report-same-number"
                page.evaluate("""({otherJob, duplicateId}) => {
                    const key = "axiom_public_erp_suite_v1";
                    const demo = JSON.parse(localStorage.getItem(key));
                    const original = demo.quality.find(q => q.id === demo.quality[0].id);
                    demo.quality.push({
                        id: duplicateId, number: original.number, jobId: otherJob,
                        reason: "Illustrative second-job observation", status: "OPEN",
                        openedAt: "2026-11-01T12:00:00Z", closedAt: null,
                        inspections: [], correctiveActions: [], followUps: []
                    });
                    localStorage.setItem(key, JSON.stringify(demo));
                }""", {"otherJob": other_job, "duplicateId": duplicate_case_id})
                page.goto(f"http://127.0.0.1:{server.server_port}/erp/#reports")
                page.locator("#report-select").select_option("quality")
                report_buttons = page.locator('button[data-action="report-quality-case"]')
                expect(report_buttons).to_have_count(2)
                expect(report_buttons.nth(0)).to_have_text(report_buttons.nth(1).inner_text())
                expect(report_buttons.nth(0)).to_have_attribute("data-id", case_id)
                expect(report_buttons.nth(1)).to_have_attribute("data-id", duplicate_case_id)
                # A mismatched row binding must fail without redirecting.
                report_buttons.nth(0).evaluate("el => el.dataset.rowIndex = '1'")
                report_buttons.nth(0).click()
                assert page.url.endswith("#reports"), "Stale report link must not change views"
                page.locator(
                    f'button[data-action="report-quality-case"][data-id="{duplicate_case_id}"]'
                ).click()
                page.wait_for_function("location.hash === '#quality'")
                expect(panel).to_have_attribute("data-case-id", duplicate_case_id)
                expect(page.locator("#job-context")).to_have_value(other_job)
                page.locator('#module-nav a[data-nav="reports"]').click()
                page.wait_for_function("location.hash === '#reports'")
                page.locator("#report-select").select_option("quality")
                page.locator(
                    f'button[data-action="report-quality-case"][data-id="{case_id}"]'
                ).click()
                page.wait_for_function("location.hash === '#quality'")
                expect(panel).to_have_attribute("data-case-id", case_id)
                expect(page.locator("#job-context")).to_have_value(job_id)
                assert not page_errors, f"Browser JavaScript errors: {page_errors}"
                print("PASS: Quality Forge navigation, duplicate-number report identity, native context menus")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
