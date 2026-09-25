# Repository Audit and Consolidation Map

Audit date: 2026-09-24

| Repository | Latest audited commit | What SuperForge takes from it |
|---|---|---|
| ForgeVault | `f222843` | document/version/release/audit concepts, JobBOSS handoff direction |
| EZ-FAIR | `8a75fa1` | PDF characteristic extraction, ballooning, FAI workbook generation |
| venvWin | `ee5ea82` | reviewed; separate OS/compatibility product, not coupled to manufacturing runtime |
| BEAN | `ed96879` | supervised optimization, evidence, memory/outcome learning principles |
| ForgeQC | `b847456` | quality workflow, CAPA, KPI/PPM, ERP ingest, hash-chained persistent audit |
| PM-Tracker | `c171fce` | machine/task/completion PM workflow behavior |
| MFGForge | `f30b806` | ERP/manufacturing chassis, module map, quoting/planning intelligence |
| SuperForge_Unofficial | `41a034d` | branch base and release identity |
| EZ_Expedite | `9cb4ae3` | occurrence tracking, action ownership, due dates, escalation and system links |

## Consolidation rule

Old repositories remain provenance and migration sources. New cross-module business logic belongs in SuperForge.

No module may become a disconnected second database island.

Every native module must use:

1. shared entity identity
2. shared event ledger
3. shared audit chain
4. shared context navigation
5. explicit source/target relationships
6. human review for critical AI/learning actions

## Source migration priority

1. Quality Forge
2. ERP/job/PO/inventory/clocking core
3. EZ FAIR
4. PM
5. Vault
6. Expedite/action routing
7. quoting/planning
8. BEAN supervised learning
9. packaging and installer

## Important finding

ForgeQC already proved the correct audit direction: persistent ProgramData storage plus a hash-chained journal. MFGForge already proved the correct host direction: one manufacturing app with cross-module intelligence. This branch combines those two ideas instead of choosing one and discarding the other.
