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
| Preventive maintenance | Includes the separate PM Tracker's core public workflow concepts: invented machine register, recurring task schedules, due/overdue calculations, completion history, follow-up requests and CSV export. Browser-only, no real asset connections |
| Document control | Adjusts fictional drawing revision to test mismatch and match behavior; this is not a true release/signature |
| ERP emulator | Imports independent invented job and routing fixtures and issues fake acceptance receipts for completed browser-local clock sessions |
| Reports | Eight browser-local, functional report views covering jobs, inventory, POs, quality, labor, PM, maintenance requests and events, each with full CSV export |
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

## PM Tracker integration boundary

Axiom includes a historical source snapshot under `components/source_snapshots/PM-Tracker/app.py`, while the maintained standalone PM-Tracker repository has its own Flask/SQLite and Excel-file functionality. This new `web/erp/#pm` screen brings those **concepts** into the connected Axiom Pages demonstration; it does **not** merge or expose a real site-server or production maintenance database. It uses the unchanged dark Axiom ERP visual theme and new original synthetic machine/task fixtures only.

The demo supports task due dates, machine cards and shareable local machine links, PM log entries, maintenance requests and simulated closeout. Real QR scanning, workbooks, electronic signoffs, LOTO authorization, machine isolation, multi-user permissions and server data imports are not present. Completion here is a test event, not evidence that maintenance occurred. Never enter real operator or machine information.

## Axiom ERP navigation

The public `/erp/` workspace now has a scalable two-level menu organized by functional department rather than a single flat list. Menu search supports screen names and common ERP synonyms; browser-local favorites and recents let people return to frequent screens. **Ctrl+K** or **/** focuses screen search. The new Report Center (`#reports`) is a real read-only query of the existing synthetic dataset, not a placeholder page.

Menu entries are registered only for implemented browser screens. This deliberately avoids the impression that unimplemented accounting, MRP, scheduling, payroll, or other large ERP subsystems are already functional. The shell uses Axiom's existing dark charcoal, lime accent and component styles, rather than vendor-sourced branding or UI assets.

Menu preferences are isolated from the demo's production data under `axiom_public_erp_menu_v1`. They are local to the viewer's browser; accounts, shared user profiles, permission-driven menus and backend search are not implemented.

The report exports are demonstrations of ordinary browser state. None are official financial reports, production schedules, certified inspections or employee/payroll records.

## Contextual Open with and searchable menus

The public browser demo now adapts the record-aware right-click idea already implemented by Axiom's local Flask application. Right-click a **fictional record row** such as a job, stock item, purchase order, quality hold, document, machine, PM task, or maintenance request. A real in-page **Open with** menu offers only functioning browser demo modules, in relevant order. It can be searched where enough actions exist; **Shift+F10** or the keyboard Context Menu key also opens a focused record's menu. **Esc** closes it. Hold **Shift** and right-click to use the native browser context menu.

Search the module sidebar with **Ctrl+K** or **/** and terms such as `PO Tracker`, `PO Entry`, `Job Entry`, or `Part Tracker`. These terms resolve to the actual currently implemented browser modules. They are not proof that dedicated desktop-level part-master editing exists in the static demo.

Choosing a destination carries the selected fictional record, filters related records, switches the selected job or machine where appropriate, and preselects part/material on existing Work Order Entry and PO Entry forms. A current-context banner lets the viewer clear the filter. The selection is session-local UI state; the underlying fictional records remain stored in browser localStorage. The public menu never calls local Axiom Flask APIs, external ERP/JobBOSS services, real data, or a Windows Explorer shell extension.

The menu is deliberately *not* global. Native right-click is preserved on links, buttons, input fields, editable regions, and selected text. An unrecognized record is not substituted with another one, and no fictitious Part Entry or separate master-data module is promised. Only invented records and generic descriptions are used.

## Main visitor experience and Request Desk

GitHub repository README now opens with the live [Axiom ERP demonstration](https://danieloculus0-bot.github.io/Axiom_Beta/erp/). The legacy original browser lab remains accessible by its URL but is no longer promoted in the current ERP demo navigation. GitHub Pages root continues to redirect to `/erp/`.

The live **Request Desk** is browser-only, using entirely invented material, equipment, owner codes, issue types, and event notes. It includes assigned purchasing requisitions, due dates, overdue status, action logs, approval, a linked in-demo PO, and follow-up. **A purchase request remains unresolved until the linked PO is received and its receipt is acknowledged**. Issuing or approving a PO alone is not completion. The existing PO receiving action updates inventory and linked request status in the same saved browser state.

Maintenance requests reuse Axiom's existing PM request data model and are tracked in the same Request Desk with owner, due date, and follow-up history. **Closed means work completed**; a separate verification stage is deliberately not required for maintenance. Existing browser state is migrated without deleting jobs, PM schedules, or clocking data. Reporting includes the fictional purchase request follow-up register.

This demo has no emails, active reminder service, external purchasing integration, approval permissions, actual personnel assignment, live uploads or BEAN connection. It is not appropriate for entering real business or employee records. Quality management remains a limited demonstration of holds, pending the deeper native Quality Forge representation.
