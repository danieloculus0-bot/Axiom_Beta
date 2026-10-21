# Axiom Beta

Current ERP consolidation target: a local-first manufacturing operations and quality application with a shared database/event/audit structure. Do not confuse bundled source snapshots with continuously synchronized standalone apps.

[**Current 16-repository portfolio, CI status, and ownership map**](docs/CURRENT_PORTFOLIO.md)

## Axiom × BEAN — the operating model

**[Public project overview](https://danieloculus0-bot.github.io/BEAN/axiom.html)** ·
**[Managed workbook architecture](docs/MANAGED_WORKBOOKS_ARCHITECTURE.md)**

Keep the Excel-compatible editor and the existing workbook. Axiom should
retain the controlled original, interpret tables as **proposals**, and move
**approved** data into proper linked manufacturing and business records.
The goal is to retire disconnected private shadow-ERP spreadsheets, **not**
replace Excel with another new spreadsheet engine.

The present Sheet Workbench is a useful simplified grid, **not** a full-fidelity
native XLSX editor and not yet a document-revision ingestion service. That
capability is scoped in the architecture document with explicit acceptance
tests. The persistent Axiom Favorites UI and local BEAN navigation connector
are already implemented and separately verified.

## Current build state

**Reviewed:** 2026-10-20 · **Inspected main:** `bd86e7a2227c` · **Type:** working experimental/beta code; not automatically production-certified.

- [Axiom Beta CI](https://github.com/danieloculus0-bot/Axiom_Beta/actions/runs/39503062748) — **Passed** at inspected `main`.
- [Axiom Windows Installer](https://github.com/danieloculus0-bot/Axiom_Beta/actions/runs/39503062676) — **Passed** at inspected `main`.
- [Axiom Linux Package](https://github.com/danieloculus0-bot/Axiom_Beta/actions/runs/39503062597) — **Passed** at inspected `main`.
- [Controlled FAI wiring across Windows and Linux](https://github.com/danieloculus0-bot/Axiom_Beta/actions/runs/39503062544) — **Passed** at inspected `main`.

[See live Actions](https://github.com/danieloculus0-bot/Axiom_Beta/actions) for newer results; this is a dated evidence snapshot, not a continuously updated indicator.

## Implemented today

- Native Flask/SQLite workspaces for manufacturing, quality, methods, documents, preventive maintenance, reporting and other modules.
- Verified cross-repository **ForgeVault → EZ-FAIR → Axiom** controlled drawing workflow: released PDF checksum, exact version/package/revision, extracted **review-required** characteristics and idempotent FAI import.
- Existing EZ Methods plans can link to the exact ForgeVault version **only after** a matching controlled FAI import and released document record; mismatched part/revisions are rejected. This is source traceability, not automatic routing approval.
- Gothic Lime workbench; source provenance visible in the FAI list. Actual Linux and Windows CI/packaging workflows.

## Run and verify

See the [archived complete setup instructions](docs/archive/README_2026-10-20_before_refresh.md) for Windows/Linux install details. The source application exports `create_app` in `superforge/app.py` and exposes `/health`. Run project tests with `python -m pytest -q` after installing development dependencies.

## Known boundaries

- Public shared-network deployment still needs real authentication, permissions and trustworthy identity attribution; an actor string is not authentication.
- Integration tests prove local versioned contracts on synthetic data, not an authorized live shop ERP connection or a completed human inspection.
- [MFGForge](https://github.com/danieloculus0-bot/MFGForge) is the earlier source line; [SuperForge Unofficial](https://github.com/danieloculus0-bot/SuperForge_Unofficial) is artifact/planning, not another live ERP.

## Next engineering work

Strengthen authentication and durable API boundaries; expose controlled import via a properly authenticated workflow, then validate installation with actual shop data.

## Documentation

- [Suite design standard](docs/BEAN_GOTHIC_LIME_DESIGN.md)
- [Verified engineering suite implementation ledger](docs/ENGINEERING_SUITE_PROGRESS_2026-10-20.md)
- [Controlled FAI wiring workflow](.github/workflows/controlled-fai-wiring.yml)
- [Portfolio audit (historical snapshot)](docs/PORTFOLIO_AUDIT_2026-10-20.md)
- [**Complete prior README, including history and detailed instructions**](docs/archive/README_2026-10-20_before_refresh.md)

Historical experiments, dated reports and superseded architectural claims have been moved out of this landing page, **not deleted**.

## Suite-wide pre-build audit and live connector boundaries

[**October 20 README, connector and demo readiness audit**](docs/BUILD_READINESS_SWEEP_2026-10-20.md) documents all 16 portfolio repositories, branch-aware CI receipts, public-demo limitations, missing native ERP adapter mappings and the recommended single-job end-to-end acceptance test.

**Latest connector checkpoint:** The local EZstimate/ForgeVault/Axiom/BEAN quote-import integration workflow has been updated to consume the tested current EZstimate source instead of the previous pinned alpha. The refreshed [Windows/Linux wiring job](https://github.com/danieloculus0-bot/Axiom_Beta/actions/runs/39516325217) passed. Its coverage is **controlled source → estimating draft → Axiom review-required quote**, not supplier purchasing or native ERP request acceptance.

**New, separate EZstimate purchasing component:** The independent local EZstimate runtime supports material request drafts, recorded approval and CSV/JSON or configured HTTPS PR delivery. This capability is **not yet consumed by an Axiom native requisition connector** and does not create supplier purchase orders. See [the original adapter contract](https://github.com/danieloculus0-bot/EZstimate/blob/main/docs/ERP_PURCHASE_REQUESTS.md) and the [reconciliation matrix](docs/BUILD_READINESS_SWEEP_2026-10-20.md).

## EZstimate quote proposals

The Axiom quoting workspace now shows the original ForgeVault drawing/version, release package and PDF hash for quote proposals imported by the local ezstimate_quote integration. Quote math is independently recalculated; differing totals and conflicting quote numbers are rejected. Every imported proposal remains review_required and is never a customer-approved quote or PO. The cross-platform integration test uses actual EZstimate, ForgeVault and BEAN source checkouts. An authenticated shared-network write API is NOT implemented.

## BEAN navigation and favorites (experimental)

Axiom now exposes a real persistent **Favorites** menu in its Gothic Lime sidebar.
Click `☆ Favorite` inside an existing workspace to pin it, or use the
`/favorites` page to inspect and remove saved destinations. Favorites survive
application restarts in the local Axiom SQLite database. Only registered Axiom
workspaces are supported; BEAN must not invent paths or confirm a pin without a
successful database write.

For local tools and a future authenticated ChatGPT/BEAN connector:

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/navigation?q=quality` | GET | Search registered workspaces, return key, label and relative path |
| `/api/favorites` | GET | List saved workspaces |
| `/api/favorites` | POST JSON `{"module_key":"quality"}` | Idempotently pin existing module |
| `/api/favorites/{module_key}` | DELETE | Remove existing pin |

This is a **local single-user** feature. These routes are not public
authenticated account APIs. Do not expose the Axiom Flask service directly
to the internet; production ChatGPT integration still requires authenticated
user identity, a secured HTTPS boundary, and a connector that can reach
the Axiom application. The separately hosted ChatGPT app cannot reach
`localhost` on the user's workstation by itself.

Tests: `python -m pytest tests/test_favorites_navigation.py -q`.
