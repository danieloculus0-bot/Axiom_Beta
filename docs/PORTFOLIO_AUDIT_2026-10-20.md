# Repository portfolio audit, 2026-10-20

**Scope:** 15 repositories owned by `danieloculus0-bot`, all on `main` and unarchived at inspection. This is a rapid source-tree, README, workflow and selected implementation review, **not** a comprehensive security, integration, safety or product validation audit. A green CI job confirms only what that job exercises, not deployment or end-user readiness.

## Portfolio inventory

| Repository | Verified source-level role | Outstanding or uncertain |
| --- | --- | --- |
| [64Δ](https://github.com/danieloculus0-bot/64-) | Static 8×8 browser board, human-facing pawn/map workflow, separate Python deterministic causal-move research engine | Prototype has unrestricted board moves; Python causal law is not enforced by the browser UI; no recorded GitHub Actions runs in inspected history |
| [AIscend](https://github.com/danieloculus0-bot/AIscend) | Windows/Flask trading experiment, Base/Coinbase Advanced order adapters, persistence and experimental strategy research; successful recent research workflows | Research tests do not prove real trading profitability or that a deployed instance is running |
| [Axiom Beta](https://github.com/danieloculus0-bot/Axiom_Beta) | **Current ERP consolidation target**, event/audit infrastructure and native modules for quality, methods, finance, leadership, reporting, automation and integrations; successful Sep 25 CI/package jobs | Vendored/source snapshots are not proof of live bidirectional integration, production migration or deployment |
| [BEAN](https://github.com/danieloculus0-bot/BEAN) | Persistent experimental reasoning/memory system with numerous evidence and autonomy labs; core regression passed Oct 18 | Oct 20 autonomous code-author self-repair workflow **failed** independent Linux/Windows validation; no qualifying fix promoted |
| [BEAN AI Bridge](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-) | Generic, synthetic-data ERP evidence ingestion, ledger/replay/KPI and experimental learning/repair labs; metamorphic checks passed Oct 20 | Oct 20 novel repair run **failed** while requesting usable model-authored candidate; no automatic repair accepted; no live ERP connector |
| [EZ-FAIR](https://github.com/danieloculus0-bot/EZ-FAIR) | Desktop assisted drawing characteristic extraction and FAI workbook/PDF creation with editable review | Last visible passing GitHub test run was Sep 25, before newer Oct 16 source updates; current head needs a new CI run and real drawing validation |
| [EZ-FEA](https://github.com/danieloculus0-bot/EZ-FEA) | Gmsh/CalculiX real 3D linear-static solver, multiple face fixtures and loads, force-balance checks, three reproducible monolithic frame specimens; native solver CI passed Oct 20 | Not a validated engineering sign-off tool; no real joints, contact, multi-part assemblies, nonlinear physics or mesh-convergence evidence |
| [EZ Expedite](https://github.com/danieloculus0-bot/EZ_Expedite) | Standalone GPL no-cost case ownership, actions, deadlines, RMA/quality expediting; Oct 18 smoke CI passed | ERP integrations are separate/future; earlier successful installer CI should not be mistaken for a new release at current HEAD |
| [ForgeQC](https://github.com/danieloculus0-bot/ForgeQC) | Standalone quality records, RMA/NCR/CAR workflow and quote/material review; Sep 24 smoke/build success | Axiom source snapshot does not automatically mean live integration or migration is complete |
| [ForgeVault](https://github.com/danieloculus0-bot/ForgeVault) | Local PDM versioning, check-in/out, releases, reviews, index/search, JobBOSS² outbox export; CI, tests and desktop workflow passed Sep 25 | A separate Windows smoke/build workflow failed on missing Cairo library during icon generation; physical shop deployment not proved |
| [FUN](https://github.com/danieloculus0-bot/FUN) | Emperor Gauntlet browser game and original Pygame prototype; latest Pages publication and browser test runs passed | Independent game repository, not an ERP module; browser and mobile play testing still matters |
| [MFGForge](https://github.com/danieloculus0-bot/MFGForge) | Earlier SuperForge ERP Flask/SQLite source base; smoke passed Sep 25 | README's earlier “canonical source” role is historical; **Axiom Beta is the newer consolidation target**. No automatic replacement of MFGForge deployments |
| [PM-Tracker](https://github.com/danieloculus0-bot/PM-Tracker) | Standalone PM scheduling, QR machine views, import/export, work orders and Windows Server packaging; Oct 15 smoke and release CI passed | Generic app does not validate site-specific machine isolation/LOTO or imply a production server installation |
| [SuperForge Unofficial](https://github.com/danieloculus0-bot/SuperForge_Unofficial) | Artifact manifest/planning repository; no significant application source in inspected tree | No recorded Actions runs; should not be advertised as a compiled or released ERP |
| [venvWin](https://github.com/danieloculus0-bot/venvWin) | GPL no-cost Windows compatibility capsule and experimental portable Linux shell architecture; Oct 18 tests/preflight/branding passed | Physical boot and actual compatibility coverage remain separate unproven product gates |

## Ownership and integration boundaries

- **Axiom Beta** is the canonical *ERP consolidation target*. **MFGForge** and **SuperForge Unofficial** remain historically important source and artifact lines respectively. Do not treat all three as independent completed ERP releases.
- **ForgeVault** is the PDM/document custody subsystem. **EZ-FEA** owns physics, **EZ-FAIR** owns inspection characteristic extraction and FAI document creation, and **ForgeQC** owns quality-specific source workflows unless explicitly migrated.
- **EZ Expedite** owns action/case follow-up, **PM-Tracker** owns maintenance operations, and **BEAN AI Bridge** owns generic reporting/evidence replay. A future integration must define exact read/write contracts, permissions, and source-of-truth boundaries.
- **BEAN Core** can be an advisory learning and reasoning layer. Experimental, rejected, and failing self-repair labs do not equate to accepted autonomous production code changes.
- **AIscend** is a separate autonomous trading experiment. **64Δ**, **FUN**, and **venvWin** are separate research/game/OS lines, not assumed live modules of the ERP suite.

## Immediate follow-up priorities

1. Fix and rerun BEAN Core's independent self-repair validation; do not promote unverified generated code.
2. Diagnose BEAN AI Bridge's failed novel-repair draft path and preserve the rejected source/validation receipts.
3. Remove or replace ForgeVault's Windows icon-generation Cairo dependency, or document/install its actual runtime.
4. Re-run EZ-FAIR CI at latest source HEAD and validate real drawings, title-block tolerances and rotated annotation cases.
5. Define cross-repository schemas for controlled CAD/model revision references, FEA results, drawing/FAI revisions, quality events and audit provenance. Keep execution in owning systems.
6. Continue EZ-FEA mesh-convergence verification, connectors and multi-part assemblies without claiming welded/bolted/pinned physics prematurely.

## Audit maintenance rule

This file captures evidence seen on **2026-10-20**, not a continuous CI feed. Read the live Actions pages and current source before relying on these statuses for a release or decision. Claims in project READMEs should be labeled **implemented**, **bench-tested**, **experimental**, **planned**, or **unverified**, with source or CI evidence.
