# Axiom Connected Browser ERP Demonstration

**Everything in this public site is fictional.** No employer, customer, supplier, drawing, work instruction, job number, employee, site configuration, API token, contract or manufacturing transaction from any real business is used.

## Navigation

- Site root redirects to **/erp/**, the connected ERP workbench.
- **/ewi/** is the larger stand-alone clocking and illustration viewer. It now loads the *same browser-local fictional job dataset* if that dataset exists, and shares its time sessions with the ERP suite.
- **/lab/** preserves the earlier estimate/inspection browser exercise.

## What actually works on GitHub Pages

| Module | Functional demonstration |
|---|---|
| Dashboard | Aggregates the shared sample jobs, open purchase orders, blocking conditions and recorded clock sessions |
| Work orders | Creates work orders from three invented catalog items and selects job context across modules |
| Routing | Displays the job-specific, entirely fabricated operation list and links to the operator terminal |
| EWI | Renders an original generic plate illustration beside work steps; blocked source revisions/holds prevent starting the browser clock |
| Clocking | Starts and stops real elapsed-time sessions, prevents a duplicate active clock by fictional operator code and exports records |
| Inventory | Computes on-hand, reserved and available material; applies job reservations |
| Purchasing | Issues invented purchase orders and receives them into the same inventory balance |
| Quality | Creates and closes synthetic nonconformance holds that affect the selected job's EWI readiness |
| Document control | Adjusts fictional drawing revision to test mismatch and match behavior; this is not a true release/signature |
| ERP emulator | Imports independent invented job and routing fixtures and issues fake acceptance receipts for completed browser-local clock sessions |
| Events | Provides an append-order, **not immutable**, local action history and export/reset options |

The in-browser "ERP emulator" has a conceptual REST-shaped contract for explaining integration boundaries; it is a JavaScript mock, **not a JobBOSS² replica or HTTP server**. It provides **no live network/API endpoints**, ERP data access, or credential handling. No session is actually submitted to JobBOSS². The production Axiom Windows desktop/backend architecture remains separate and requires authorized ECI integrations.

All synthetic state is saved in the same browser's localStorage under \`axiom_public_erp_suite_v1\` and \`axiom_ewi_public_demo_sessions_v1\`. This is convenient demo persistence, *not* a multi-user database, durable audit ledger, access-controlled ERP or authenticated clock. Data may disappear when browser storage is disabled or cleared. Open multiple browser tabs may contend with each other; no cross-machine consistency is promised.

**Do not put real business data or real employee identifiers into this public demonstration.** Inputs for the new ERP suite are restricted to prewritten fictional catalog records, dropdown reasons and numeric values. The EWI clock accepts only \`DEMO-\` prefixed operator codes.

## Test coverage

Run locally in a checkout:

\`\`\`powershell
node --test web/engine.test.mjs web/ewi/engine.test.mjs web/erp/engine.test.mjs
\`\`\`

Automated tests cover purchase order receipt updates, stock reservations and shortages, drawing-revision holds, quality hold release, simulated external import idempotence, duplicate simulator receipts, clock session handoff and starter jobs shared with standalone EWI.

GitHub Pages only hosts the static site. The GitHub Actions publishing workflow needs a correctly configured GitHub Pages environment and permission; a successful git commit alone does not establish a live URL.
