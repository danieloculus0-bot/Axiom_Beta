# Axiom EWI desktop: operator station (beta)

This module is part of Axiom, not a separate ERP. The dedicated `Axiom-EWI.exe` built by the Windows workflow launches the same localhost Axiom service directly at `/ewi`. The standard Axiom desktop app also includes an **Electronic Work Instructions** navigation item. The dedicated launcher starts its own local server, so do not launch both executables against port 5060 simultaneously.

## Two controlled inputs

1. **JobBOSS² hosted Public API, read-only**: `GET /api/v1/order-routings` supplies job-scoped operation steps, work center and textual instructions. The read uses a requested job number and rejects records from other jobs. Axiom stores a local snapshot, not a copy of an actual customer record in the public repository. API access must be enabled and approved by ECI.
2. **Controlled drawing vault, local file**: Axiom's existing `jobs`, `parts` and `documents` tables provide an *explicitly job-linked* record with status `released`, matching part revision, PDF file reference and SHA-256. The file must be under the local configured approved root. A part-only document never constitutes authorization for a job. The app rehashes the PDF on every view and start event.

The operator screen blocks starting work when the drawing source is missing, its checksum or revision disagrees, the ERP routing does not match the part, or the job is closed/on hold. The PDF never leaves the user's configured local storage.

## Secure configuration (Windows)

Configure with your administrator; values below are **placeholders**, not real credentials. Set locally on the machine, not in source control, issue threads or screenshots. ECI API activation varies by deployment.

```powershell
$env:AXIOM_EWI_DOCUMENT_ROOT = 'D:\ApprovedDocs'
$env:AXIOM_JB2_CLIENT_ID = '<ECI-issued client ID>'
$env:AXIOM_JB2_CLIENT_SECRET = '<ECI-issued client secret>'
.\Axiom-EWI.exe
```

Axiom must already have jobs, parts and job-linked document records imported or created through its existing controlled workflows. `storage_reference` can be a root-relative PDF path (recommended), or an absolute path inside the configured root. The checksum must be the PDF's actual SHA-256. Other file types are refused.

The connector uses ECI's official OAuth2 client-credentials token endpoint and its hosted order-routings REST endpoint. For installations without supported Public API access, use an approved *read-only* SQL/reporting or export integration in a future adapter. **Do not write to the ERP database directly.** Installation type, ECI permissions, field mappings and the time-ticket write contract require testing against an authorized non-production environment.

## Clocking behavior and limitations

- Clock start and stop work **locally now**. One active session per entered employee code is enforced by SQLite. UTC timestamps and unique event IDs are persisted in `ewi_clock_sessions` and `ewi_outbox`, with audit events.
- The outbox is **pending reconciliation**, not a JobBOSS time ticket. Nothing is automatically transmitted to the ERP, nor is any timesheet, payroll entry, job completion, or quantity posted.
- Entering an employee code is not authentication. Do not rely on this alone for production labor authorization; add authenticated badges/PIN or server identity and operator-specific permissions before deployment. Shared-mode authenticated `operations` and `admin` users may access EWI writes; local desktop mode is loopback-only.
- Start/stop error messages are returned in the GUI. ERP sync failure retains the prior route snapshot. This is an experimental beta for workstation validation, not a production clock-in replacement.
- Deployment across several operator stations requires a central, authorized database/service and concurrency handling; the local SQLite clocking state is not shared across machines.
- The next stage requires ECI confirmation of time-ticket write endpoints and approved reconciliation logic, plus operator identity, shift handling, offline recovery, hold-point approvals and production acceptance testing.

No customer drawings, ERP dumps, staff records, credentials, or company-specific routing data belong in this repository or its build artifacts. The tests use only invented synthetic fixtures.
