# Axiom Integration Gap Audit - 2026-09-24

This pass compared Axiom's current native runtime with the live upstream repositories for BEAN, EZ-FAIR, EZ Expedite, ForgeQC, ForgeVault, MFGForge, PM-Tracker, and the SuperForge lineage. The purpose is not to recreate every legacy screen. It is to identify where Axiom currently claims or implies a connected capability that is missing, reduced to a shell, or using an inconsistent contract.

## Fixed in this pass

- Context identity is repaired for workflow actions, PPAP packages, quote intakes, payroll employees/runs/items, finance journals/accounts, sheets, organizational records, decision protocols, module suggestions, corrective actions, and audit-event detail.
- PPAP, Quoting, Planning, and quality-detail action tables no longer masquerade as the wrong entity type when opened through the universal right-click context system.
- Approved ISO-Hungry cash recognition can now be explicitly imported into a draft payroll run. Import is human-triggered, idempotent, auditable, and follows the recognition lifecycle through payroll approval and payment.
- Integration-service operational evidence uses Axiom product identity instead of leaking the old SuperForge product name.
- Current Windows audit-data documentation reflects Axiom's per-user default while retaining legacy-path compatibility.

## P0 before multi-user payroll / accounting deployment

### Authentication and role authorization

Axiom has an organizational graph and authority levels for routing decisions, but it does not yet enforce user identity or role authorization on payroll, accounting, executive-protocol, quality, or configuration mutations.

EZ Expedite already contains Microsoft Entra/MSAL sign-in and delegated Microsoft Graph patterns that can be adapted into Axiom. Axiom needs one identity layer, mapped to `org_people` / `org_roles`, with route/action authorization and audited denials. Organizational routing is not authorization until this exists.

### Backup, restore, and migration

Installers correctly preserve operational data on normal uninstall, but persistence is not backup. Before Axiom becomes the system of record for payroll, accounting, document control, or production evidence it needs verified backup, restore, database migration/versioning, and recovery tests.

## P1 source capability parity

### ForgeVault

Axiom currently exposes document metadata and has a `document_versions` table, but the native Vault does not yet provide the upstream ForgeVault behavior for content-addressed storage, SHA-256 file objects, checkout locking, controlled check-in, version chains, review requests, lifecycle, ingestion, and search.

Next integration should preserve Axiom's canonical IDs/event spine while migrating the useful ForgeVault lifecycle services rather than embedding a second vault database.

### EZ Expedite / Microsoft 365

Axiom has generic workflow actions and organizational routing, but it does not yet have the upstream EZ Expedite Microsoft 365 surface: Entra sign-in, Outlook email, Teams chat notifications, role/delegate notification delivery, and authorized action advancement.

This should become a shared Axiom identity/notification service, not an EZ-Expedite-only subsystem.

### ForgeQC remote quality intake and shipment denominator

ForgeQC upstream has a guarded remote NCR reporter, a live quality-summary endpoint, duplicate-safe ERP import archiving, and shipment ingestion. Axiom's quality core is stronger structurally, but it lacks a remote NCR intake surface and a clean shipment transaction denominator for PPM.

Current `quality_records.quantity_shipped` makes shipped quantity live on quality records. A production-grade PPM model should consume shipment transactions by period/customer/part and derive the denominator once.

### MFGForge material / capacity intelligence

Axiom's executive protocol engine is more general than the old signal builder, but several source signals are not yet backed by native transactional workflows: material certificates, supplier lead-time performance snapshots, machine utilization/capacity snapshots, BOM-review-to-quote flow, and FPY-driven planning risk.

The executive layer should not outrun the evidence feeding it.

## P1 schema-to-workflow gaps

The canonical database already contains structures that the UI only partially exercises:

- `pm_tasks` and `pm_completions`: PM page is still primarily machine registration/listing.
- `inventory_transactions`: no complete receive / issue / adjust / transfer operator workflow.
- `document_versions`: no native controlled version/check-out workflow yet.
- `fai_runs`: EZ FAIR page is mostly a runtime list despite the integrated extraction/writer engines.
- `ppap_packages`: PPAP page is currently list-oriented.
- `quote_intakes`: Quoting is currently list-oriented and does not yet carry the upstream material/BOM intelligence through a full quote lifecycle.

These are not duplicate-architecture problems. They are unfinished operator workflows over canonical data that already exists.

## P1 finance depth

The new finance core provides balanced double-entry journals, payroll clearing/payment, chart of accounts, trial balance, and a controlled sheet staging surface. It does not yet provide AP bills, AR invoices/receipts, bank reconciliation, period close, or tax/localization engines.

Keep those as additional feeders into the same journal. Do not create a second accounting truth.

## P2 integration adapter depth

Axiom's adapter contract is sound but current built-in entity ingest is limited to jobs, purchase orders, inventory items, customers, suppliers, parts, machines, and clocking errors.

Gaps include quality records, shipments, documents, BOM/material data, and other canonical entities. Flat-file integration supports CSV/JSON directly; XLSX currently enters through the Sheet Workbench rather than the generic integration adapter. The built-in SQL adapter is SQLite-only and intentionally requires a custom approved DB-API/ODBC adapter for other databases.

## Architecture rule from this audit

The strongest part of Axiom is already the shared nervous system. Future migrations should move useful source-app behavior behind the existing Axiom event bus, entity/context IDs, audit journal, organizational graph, suggestions, workflow actions, and supervised learning contracts.

Do not import a second truth database, a second event bus, a second audit journal, or a second identity system just because an upstream app already has one.
