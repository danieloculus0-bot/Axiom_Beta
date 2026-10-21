# Axiom managed workbooks — familiar Excel files, governed company data

**Published architecture direction · October 20, 2026**

The objective is **not** another spreadsheet engine. People should continue
opening, viewing and editing real Excel-compatible files in a familiar UI,
while Axiom owns the *managed document and its approved operational data*.
This gives us light, inexpensive computers and eliminates the need to run
business operations from disconnected personal spreadsheets.

## Design rule

**A spreadsheet is both a document and a potential source of operational data.
Those are different things.**

- The workbook file remains a first-class artifact. Preserve its original
  bytes, filename, worksheets, formatting, formulas, hidden sheets, defined
  names, and version history. Do not reconstruct or overwrite the workbook
  from a simplified table projection.
- The spreadsheet viewer/editor can be native to the user's device (e.g.,
  LibreOffice Calc on supported Linux/Jetson, Excel on Windows) or
  integrated via a verified document service. There is **no mandate** to
  develop another formula engine, desktop office suite, or separate
  spreadsheet system.
- Axiom is the **authoritative owner of approved imported business records**
  such as part master records, quality observations, work orders and
  purchasing data. It is **not** allowed to silently treat uploaded cells
  as those authoritative records.
- Preserve explicit links between a managed workbook revision and the
  resulting imported records. Editing the workbook does not silently
  rewrite a previously approved ERP fact.

## Desired user experience

1. Open **Documents** or **Sheets** in Axiom; locate a workbook by name,
   related job, department or part. View the latest managed revision.
2. Choose **Open in editor**. On a compatible desktop, use the installed
   Excel-compatible native editor; alternatively offer a supported in-app
   viewer/editor when its fidelity is verified.
3. Save the edited file as a **new Axiom document revision**. Do not assume a
   browser download is a synchronizing file editor; desktop handoff requires
   a verified save-back path.
4. Axiom scans workbook sheets and proposes **candidate** tables and schema
   mappings. The user sees a source preview, field matches, exceptions and
   target modules. No invented columns or hidden coercions.
5. Import reviewed rows into the authorized target module and write a
   receipt containing workbook revision hash, worksheet, row IDs, mapping
   version, duplicate handling, actor identity, and outcomes.
6. Continue working in the workbook if desired. A changed version proposes
   a new reconciliation; it does not magically replace approved records.

The workflow accepts existing `.xlsx` files. Legacy `.xls`, macro-bearing
`.xlsm`, external formula links and unsupported features need explicit
compatibility reporting. Never execute imported macros or trust cells as
commands. Reconciliation must account for formulas, cached results and
worksheet-specific interpretation.

## Actual starting point — implemented in Axiom today

Axiom Beta already has a [Sheet Workbench](../superforge/modules/finance_ui.py)
and import/export functions in
[finance.py](../superforge/modules/finance.py):

- CSV, XLSX and XLSM import into a simplified in-app grid.
- Editing grid cells and exporting CSV/XLSX.
- A bounded formula evaluator for the simplified row-based model.
- Specific approved accounting and payroll staging/posting paths.
- Local SQLite and an audit/event spine.

**Current limitation:** The existing importer reads the **active worksheet**
and replaces the Sheet Workbench's simplified grid. Its exporter builds a
**new workbook**. This is not a lossless XLSX file viewer/editor, not an
all-worksheet document repository, and not a universal source-to-ERP importer.
The original multi-tab workbook must be retained separately before any
production claim of full fidelity.

The [Favorites menu](../superforge/favorites.py) and the
[BEAN navigation connector](https://github.com/danieloculus0-bot/BEAN/blob/main/integrations/chatgpt/axiom_server.py)
are working independent foundations; they are not equivalent to a completed
workbook acquisition service.

## Lightweight implementation sequence

| Milestone | What it adds | Completion proof |
| --- | --- | --- |
| A. Managed original | Store original file unchanged and link its hash and revisions to a controlled Axiom document | Download the exact bytes after multiple reopens and revisions; compare SHA-256 |
| B. Lightweight viewer/edit | Native Calc/Excel handoff or a verified embedded editor; no replacement spreadsheet engine | Two-sheet workbook retains formulas, formatting and links across save/reopen |
| C. Interpret-only stage | Extract candidate tables from workbook sheets; show schema and confidence notes | Unmapped columns/rows never enter business tables |
| D. Target module mapping | Versioned mappings, review, stable IDs, duplicate/revision handling | Reimport is idempotent, complete audit receipt, no unapproved change |
| E. BEAN assistance | Suggest navigation and source-aware mappings; evaluate conflicts and outcomes | Only source-backed proposals; record confirmed app action separately |

## Desktop and JetPack compatibility

For ARM64 Linux, prefer native office packages already supported by the
distribution and enough free RAM for a GUI desktop. **Do not depend on Wine
running x86 Windows Office on the Jetson Nano.** A headless Axiom shop server
can serve the same browser interface to desktop clients running Excel or Calc.
A thin tablet may use an authenticated document-editing service later.

The original NVIDIA Jetson Nano is tied to JetPack 4.x with an older Ubuntu
base. Test that model separately from modern Jetson Orin devices. Neither the
ARM64 editor integration nor a production-ready JetPack installer has been
demonstrated on real hardware in this project.

## Enterprise acceptance criteria

- One controlled source workbook and a versioned shared destination—no
  personal spreadsheet silently becomes the source of truth.
- No data loss to unsupported workbook features; fidelity failures are
  explicitly surfaced, and originals are always retrievable.
- Workspace authorization, revision history, audit receipts, deduplication,
  tested rollback and backup/recovery.
- The workbook remains independently usable; Axiom contains approved,
  searchable records with source references.
- Actual Jetson and x86 PC testing, not a mock browser screenshot.

This is a **public product contract**. The full managed-workbook lifecycle
and generalized Excel-to-business-data ingestion are not implemented yet.
