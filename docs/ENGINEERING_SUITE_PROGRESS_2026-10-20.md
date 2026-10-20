# Engineering suite — implementation ledger
## Verified October 20, 2026 milestones

This is an engineering status snapshot; CI verifies specific test coverage, not deployed production operation.

| Source/project | Implemented evidence | Scope limits |
| --- | --- | --- |
| ForgeVault | SHA-256 checked atomic local object storage; release package/version verification and read-only PDF handoff; Windows/Linux storage tests and Windows EXE build passed | Shared-user authentication, recovery drills, remote storage and actual shop deployment remain unverified |
| EZ-FAIR | Released-drawing SHA-256 receiver, actual PDF characteristic extraction, review-pending handoff; desktop Gothic Lime palette and headless theme checks passed | OCR/GD&T false positives and actual drawing accuracy still need a curated shop validation set |
| Axiom | Received FAI characteristics/provenance visible at /ez-fair; a verified source version can link into an existing EZ Methods plan; Windows/Linux 3-repo integration passed | FAI proposals are **not** approved/recorded measurements; shared-deployment identity isn't solved |
| BEAN Core / BEAN site | Charcoal/steel/lime site with original smiling sprout artwork; core regression and Windows installer passed | Experimental autonomy research is not a production reasoning guarantee |
| BEAN AI Bridge | Pinned source checkout integration of real Bridge evidence and EZ-FEA inbox into BEAN Core; Windows/Linux × Python 3.11/3.12 matrix passed | Not an authenticated live ERP bridge |
| EZ-FEA | Native multi-face 3D CalculiX tests, frame specimens, and real three-grid mesh sensitivity report pass | Mesh stability is not independent engineering validation; joints/contact/multi-part not complete |

## Data custody, independent engines

ForgeVault owns immutable document versions and release evidence. EZ-FAIR interprets a specific PDF **for human review**. Axiom stores the FAI run, characteristics, quality context and provenance. EZ Methods holds routing plans and can reference previously verified source drawing versions, but drawing references do not automatically authorize a routing.

Each subsystem runs without requiring BEAN. BEAN may reason about data it receives with source uncertainty preserved; it never substitutes for a solver result or a person approving a released product.

## Unified visual language

BEAN Gothic Lime design reference: [docs/BEAN_GOTHIC_LIME_DESIGN.md](BEAN_GOTHIC_LIME_DESIGN.md). Base colors are `#0F1113` (background), `#1A1D20` (surface), `#22282A` (secondary surface), `#79DE4B` (primary accent), and `#52A86A` (secondary accent). No orange-brand styling. Keep negative/needs-review states distinct from successful measurements.

## Concrete remaining development targets

1. **Axiom identity:** authenticated sessions, per-role authorization, derived/credible audit authorship, and tests denying unauthorized ERP writes. Existing client-supplied actor strings aren't equivalent to identity.
2. **ForgeVault recovery:** backup/restore and database–file consistency under interruptions, actual Windows PDM user tests, and remote source integrations.
3. **EZ-FAIR measurement accuracy:** gold drawing corpus (real revisions, rotated pages, welded callouts, tolerances, GD&T) with recall and false-positive tracking; no real drawings in public repos.
4. **Actual Methods/purchasing integrations:** controlled source version references, operation-level requirements and need-by dates, testable exception paths without silent approvals.
5. **UI finish:** standard dense grid, review/approved/corrupted badges, reduced-motion mascot, context navigation; expand theme to independent app surfaces without replacing their execution engines.
6. **EZ-FEA mechanics:** joints, materials, mesh-convergence against analytical/independent benchmarks and native assembler stress rendering. Don't present single-solid welded surrogates as real joint physics.
7. **Packaging and licensing:** documented terms by project and actual hardware/shop deployment verification.

Keep failures and unresolved experiment outcomes in the evidence ledger. Avoid describing source snapshots as live integrations.
