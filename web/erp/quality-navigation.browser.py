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
                page.locator('form[data-form="quality-inspection"] button[type="submit"]').click()
                inspection_id = panel.locator('[data-evidence-kind="inspection"]').first.get_attribute("data-evidence-id")
                assert inspection_id

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

                page.locator('form[data-form="quality-effectiveness"] textarea[name="note"]').fill(
                    "Synthetic post-closure effectiveness review"
                )
                page.locator('form[data-form="quality-effectiveness"] button[type="submit"]').click()
                review_id = panel.locator('[data-evidence-kind="effectiveness"]').first.get_attribute("data-evidence-id")
                assert review_id
                expect(panel.locator(".panel-head .tag")).to_have_text("CLOSED")

                for kind, evidence_id in (
                    ("inspection", inspection_id),
                    ("corrective", corrective_id),
                    ("effectiveness", review_id),
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

                    if kind == "inspection":
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

                editable = page.locator('form[data-form="quality-followup"] textarea')
                native_menu = editable.evaluate("""el => {
                    const event = new MouseEvent('contextmenu', {bubbles: true, cancelable: true, button: 2});
                    el.dispatchEvent(event);
                    return !event.defaultPrevented;
                }""")
                assert native_menu, "Native context menu must remain available in editable fields"
                assert not page_errors, f"Browser JavaScript errors: {page_errors}"
                print("PASS: 3 evidence types, closed-case return focus, wrong-job guard, native editable context menu")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
