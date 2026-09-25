# Axiom Beta

Axiom is the consolidated operating system for quality, planning, purchasing, maintenance, controlled documents, reporting, leadership, automation, and supervised intelligence.

**Canonical branch:** `main`

The goal is simple: one package, one context model, one audit spine, and no disconnected departmental islands.

## What is consolidated

- **MFGForge / SuperForge:** ERP-style master data, jobs, quoting, planning, operational intelligence.
- **ForgeQC:** NCR/DMR/RMA/CAR/CAPA/deviation thinking, KPI/PPM linkage, ERP report ingest, persistent audit patterns.
- **PM-Tracker:** machine register, PM task/completion behavior, failure-to-planning logic.
- **EZ Expedite:** occurrence ownership, action routing, due dates, escalation, external-system references.
- **ForgeVault:** controlled drawing/document identity, revision/version concepts, release/audit patterns.
- **EZ FAIR:** actual PDF dimension extraction, ballooning, and FAI workbook writer source is vendored into superforge/modules/.
- **EZ Methods:** Vantage-style methods master planning, drawing/PO requirement traceability, operation-level material/tool/gage/fixture readiness, GD&T-to-inspection linkage, and EZ Expedite purchasing triggers.
- **Leadership / Company Pulse:** cross-functional accountability, aggregate morale/workforce-health trends, recognition rewards, training incentives, and action closure.
- **ISO-Hungry reporting backend:** auditable conversion of approved reported-event recognition into payroll-ready earnings, approval batches, export hashes, and payment confirmation receipts.
- **Payroll / HR backend:** hourly and salary employees, regular/overtime pay, bonuses, explicit withholdings/deductions, pay-run approval, check/direct-deposit references, payment receipts, and automatic ledger posting.
- **Accounting Ledger:** no-frills double-entry chart of accounts, balanced journal posting, trial balance, payroll clearing and cash settlement.
- **Sheet Workbench:** lightweight spreadsheet-style grid with safe row formulas, CSV/XLSX import/export, payroll input templates, journal templates, and controlled posting into canonical modules.
- **Executive Intelligence / Learning ERP:** organization graph, role-based decision protocols, Pareto executive focus, human-governed recommendations, delegated actions, outcome capture, and supervised learning.
- **Automation:** configurable event rules create assigned, due-dated workflow actions with execution receipts while controlled process rules remain deterministic.
- **BEAN:** memory/learning direction is adapted into supervised observations and improvement proposals. Learning cannot silently rewrite production logic.

## Learning ERP direction

Axiom's differentiation is the layer between transactional data and management action: normalize input, connect context, apply controlled decision protocols, resolve ownership through the organizational hierarchy, surface the smallest set of signals that explains most current impact, convert accepted recommendations into auditable work, and learn from the result.

See [True Learning ERP Architecture](docs/TRUE_LEARNING_ERP.md).

**Product rule:** ERP records what happened. Axiom should understand what matters next.

## Non-negotiable architecture

### 1. Everything emits events

Business mutations publish domain events to a shared event ledger. Event IDs, parent IDs, and correlation IDs connect derived work across modules.

Examples:

- quality record -> containment action -> job risk -> supplier/PO review -> PPM snapshot
- FAI failure -> NCR review -> job hold review
- failed PM -> affected jobs -> planning/capacity -> quality risk
- late PO -> expediting -> inventory impact -> job risk
- inventory shortage -> purchasing -> job schedule -> quote material risk
- clocking error -> correction -> job-cost review -> BEAN observation
- ERP sync -> reconciliation -> tracker refresh -> intelligence review
- morale/company pulse -> leadership review -> BEAN trend comparison
- training completion -> audited recognition credit -> reward/vendor ledger
- configurable event match -> assigned action -> due date -> execution receipt

### 2. Everything is auditable

`%PROGRAMDATA%\SuperForge\audit\superforge_audit.jsonl` on Windows is append-only from the application's point of view.

Each entry contains:

- sequence
- UTC timestamp
- event ID
- correlation ID
- source and target module
- actor
- action and reason
- entity identity
- before/after snapshots and hashes where applicable
- previous entry hash
- current SHA-256 entry hash

The audit path is separate from application binaries. Normal uninstall logic should leave this operational evidence alone.

### 3. Right-click works everywhere

Every screen has a universal context launcher. Right-clicking a record adds record-aware destinations. Right-clicking empty application space opens the global module launcher.

Typical menu:

```text
Open with >
  Job Tracker
  Purchase Order Tracker
  Inventory Tracker
  Job Clocking Errors
  Quality Forge
  PM / Equipment
  Drawing / Document Vault
  EZ FAIR / FAI
  PPAP
  Quoting
  Planning / Capacity
  Supplier History
  ERP / Systems
  BEAN Intelligence
  Audit Trail
```

Context is carried in the URL and relevant tracker views resolve direct relationships instead of opening blank.

### 4. Quality is the center of gravity

Quality Forge is designed to become the strongest module in the suite, not a side page.

The shared schema supports:

- NCR
- DMR
- RMA
- CAR
- CAPA
- deviation
- inspection reject
- customer complaint
- supplier NCR
- 5-Why / corrective action
- containment
- disposition
- root cause
- corrective/preventive action
- effectiveness
- part/job/PO/supplier/machine links
- PPM
- inspections
- FAI
- PPAP
- linked evidence
- workflow actions

### 5. ERP integration is adapter-based

Axiom does not hard-code itself to JobBOSS².

Built-in adapter contracts cover:

- CSV/JSON report-drop feeds
- REST APIs
- approved SQL/report views
- queued outbound payloads
- field mapping and transforms
- durable external IDs
- sync-run receipts
- conflicts
- retries/outbox

That architecture can support JobBOSS², Epicor, Plex, SAP, Infor/Syteline, or a custom ERP when that system exposes an approved interface. Closed proprietary systems still require whatever export/API/database access the vendor permits.

### 6. Learning is supervised

BEAN-style learning can:

- retain observations
- measure repeated signals
- retain outcomes and human ratings
- propose rule/routing/threshold improvements
- attach evidence
- require a validation plan
- require a rollback plan

It cannot silently change production rules. Proposals remain `proposal_only` until a recorded human review changes permission.


### 7. Leadership includes morale and recognition

Leadership is treated as an operating process. The Company Pulse view combines open/overdue/unassigned work, quality load, purchasing risk, blocked method dependencies, aggregate morale signals, recognition, and training.

Morale/workforce health is stored as department/period aggregates. Recognition accounts and vending/canteen references are kept in a separate positive reward ledger.

### 8. Automation must leave receipts

Configurable automation rules match domain events and create normal workflow actions with target module, assignee, due date, source event, and execution receipt.

Automation can route work aggressively. It cannot silently rewrite controlled methods, inspection criteria, quality requirements, or ERP source data.

## Install

Axiom is packaged as a real end-user application. Normal uninstall removes program files and preserves the operational database, audit journal, attachments and integration data.

### Windows

Stable tested beta installer:

https://github.com/danieloculus0-bot/Axiom_Beta/releases/download/windows-beta-latest/Axiom_Setup_Latest.exe

The per-user installer normally does not require administrator rights and installs under:

```text
%LOCALAPPDATA%\Programs\Axiom
```

New per-user operational data defaults to:

```text
%LOCALAPPDATA%\Axiom
```

Existing Axiom or legacy SuperForge operational data under ProgramData is detected and reused rather than silently abandoned.

### Linux x86_64

Stable tested beta package:

https://github.com/danieloculus0-bot/Axiom_Beta/releases/download/linux-beta-latest/Axiom_Linux_x86_64_Latest.tar.gz

Extract it and run:

```bash
./install.sh
```

The default install is user-local under `~/.local` and does not require root. Normal `./uninstall.sh` preserves operational data. `./uninstall.sh --purge-data` is intentionally explicit.

### Payroll tax boundary

Axiom calculates gross pay, deductions, net pay, approvals, payments and accounting entries. Statutory tax withholding amounts are explicit inputs/imports until a jurisdiction-specific tax-table adapter is configured. Axiom does not invent federal, state or local withholding rules.

## Run

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open:

```text
http://127.0.0.1:5060
```

## UI

- dark by default
- neutral dark surfaces
- one configurable accent color for buttons, active navigation, and subtle highlights
- optional light mode
- no multicolor carnival UI
- global and record-specific right-click navigation

## Current build status

This repository is the canonical Axiom Beta foundation. It already contains the shared schema, event bus, audit journal, context router, ERP adapter framework, native quality services, EZ Methods, Leadership / Company Pulse, recognition and training ledgers, configurable automation, supervised learning services, and vendored EZ FAIR extraction/workbook engines.

Legacy repos remain untouched while migration continues.


## Compatibility note

The internal Python package namespace remains `superforge` during the consolidation period so the proven module imports do not get broken for cosmetic reasons. Product identity, executable naming, runtime environment variables, UI branding, CI, and release artifacts are Axiom. New runtime variables use the `AXIOM_` prefix; legacy `SUPERFORGE_` variables remain supported for continuity.


### 9. Reporting is a first-class output layer

Axiom's Reporting Center reads the same canonical operational records used by the transaction modules rather than maintaining a second reporting database.

Current export families include:

- Quality records
- Purchasing / PO risk
- Workflow actions
- KPI history
- BEAN intelligence proposals
- Domain event ledger

CSV and JSON exports are generated from the canonical records and each export leaves an audit receipt. The output layer is intentionally designed so PDF, Excel, scheduled packets, executive scorecards and customer/supplier-specific report templates can be added without duplicating business logic.

## Consolidation boundary

Axiom is now the canonical integration target. Parallel experimental cores found in older SuperForge branches are reference material only unless they are explicitly migrated behind Axiom's current event bus, canonical database, context router and audit contract. Axiom must have one nervous system, not several competing ones.
