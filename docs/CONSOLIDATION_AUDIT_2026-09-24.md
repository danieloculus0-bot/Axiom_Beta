# Consolidation Audit - 2026-09-24

> **Historical consolidation record.** During this pass, the working integration branch lived in SuperForge. Axiom is now the canonical integration target. Current source heads, release gates, and provenance are maintained in `components/SOURCE_MANIFEST.json`; this document is retained as evidence of the earlier consolidation work.

At the time of this audit, SuperForge was the working integration target for BEAN, EZ-FAIR, EZ Expedite, ForgeQC, ForgeVault, MFGForge, and PM-Tracker. Axiom has since superseded it as the canonical target.

## Verified source snapshot status

The selected vendored source files from BEAN, EZ Expedite, ForgeQC, ForgeVault, MFGForge, and PM-Tracker were compared by Git blob SHA against their live source repositories before this pass. Every selected snapshot matched its source exactly.

EZ-FAIR is integrated natively rather than under components/source_snapshots. Its current enhancement layer for title-block tolerance detection, optional offline OCR, and basic GD&T recognition is now included in SuperForge.

## Repairs in this pass

- Event subscribers are isolated from one another.
- Every subscriber invocation receives a durable delivery receipt.
- Subscriber failure marks the source event partial_failure and writes an audit record without blocking unrelated subscribers.
- A shared module suggestion queue gives modules a non-destructive way to recommend useful work.
- Accepted suggestions become normal workflow actions. Dismissals retain review evidence.
- PO, inventory, machine, Vault document, supplier, and ERP connection creation now publish domain events.
- Low-stock inventory immediately emits the existing shortage event.
- FAI completion emits an outcome event.
- Current EZ-FAIR enhancement behavior is integrated.

## Standalone source-repo CI findings

- BEAN smoke CI failed because direct test execution dropped the repository root from PYTHONPATH. Fixed upstream.
- EZ-FAIR repo-health CI failed for the same root-import reason. Fixed upstream.
- ForgeVault validation documentation tripped its own placeholder-word audit. Fixed upstream.
- MFGForge hosted-runtime verification executed from scripts/ without the repository root on sys.path. Fixed upstream.
- EZ Expedite and ForgeQC source CI were green.
- At the time of this audit PM-Tracker did not yet have its later smoke workflow. It now has standalone smoke CI; Axiom is the canonical integration gate.

## Design boundaries

BEAN remains supervised. Suggestions cannot silently modify controlled methods. ISO-Hungry does not move money. ERP adapters act only through authorized external interfaces. Optional OCR requires local OCR dependencies and a Tesseract installation.
