# Build-readiness audit: README, connectors and demos
**Audit date:** October 20, 2026 | **Portfolio:** 16 owned GitHub repositories | **Scope:** source/tree + README, integration contract, branch-aware Actions, static-demo boundaries. This is not a live shop installation or physical-device test.

## Executive finding
The suite is a functional set of experimental systems, **not a single fully installed end-to-end manufacturing execution environment**. Preserve tested modular contracts and independently functioning standalones. The next build should target one **source-traceable, read-only-first manufacturing-job vertical slice** rather than feature expansion.

**Proof already available on main:** Axiom's local source-verified ForgeVault → EZ-FAIR → Axiom FAI pipeline and ForgeVault → EZstimate → Axiom review-only quote proposal; BEAN AI Bridge tests real checked-out BEAN Core and EZ-FEA file/event handoffs; EZ-FEA native solver benchmarks and standalone joint spreadsheet; EZstimate local source-backed pricing, material-risk and approved PR **transport** (not ERP native acceptance). CI evidence is not proof of deployed site auth or production correctness.

## Connector matrix: verified versus missing

| Chain | Evidence found | Actual contract boundary | Next integration gate |
| --- | --- | --- | --- |
| ForgeVault → EZ-FAIR → Axiom | [Axiom controlled FAI Windows/Linux](https://github.com/danieloculus0-bot/Axiom_Beta/actions/runs/39506648610) | Released drawing bytes/hash/version → review-required characteristics → Axiom DB evidence | Authenticated controlled retrieval, shop-drawing recall/false-positive tests, operator acceptance |
| ForgeVault → EZstimate → Axiom | [Axiom quote wiring](https://github.com/danieloculus0-bot/Axiom_Beta/actions/workflows/ezstimate-suite-wiring.yml), [import source](../superforge/integrations/ezstimate_quote.py) | Local pinned-checkout source versions, independent Decimal quote recomputation, idempotent review-required intake | Cross-repo CI recheck at the new EZstimate pin; explicit authenticated quote release |
| MID XLSX → EZstimate | [MID adapter](https://github.com/danieloculus0-bot/EZstimate/blob/main/ezstimate/mid_adapter.py) and [tests](https://github.com/danieloculus0-bot/EZstimate/blob/main/tests/test_mid.py) | Read-only source-sheet/row preview of demand/shortage/buyer queue | Normalized material master, canonical purchasing units, job need-by and saved allocation snapshot |
| EZstimate → generic ERP request transport | [PR source](https://github.com/danieloculus0-bot/EZstimate/blob/main/ezstimate/procurement.py), [adapters](https://github.com/danieloculus0-bot/EZstimate/blob/main/ezstimate/erp_adapters.py), [passed tests](https://github.com/danieloculus0-bot/EZstimate/actions/runs/39513290822) | Local approved `axiom.purchase_request.v1` → CSV/JSON outbox or configured HTTPS endpoint | **Not integrated into Axiom's requisition entities; no ERP-assigned PR ID, real-provider acceptance receipt, or native supplier PO.** Define adapter-specific acknowledgements and identity/role authorization |
| EZstimate → BEAN Core | [EZstimate BEAN journal](https://github.com/danieloculus0-bot/EZstimate/blob/main/ezstimate/bean.py) | Optional local installed Core event persistence; warnings/outcome scorecard remain evidence-only | Verify production runtime path and compare actual holdout forecast performance; journal is not trained learning |
| BEAN AI Bridge → BEAN Core / EZ-FEA | [Bridge real-suite wiring](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/blob/main/docs/REAL_SUITE_WIRING.md) | Local checked-out source + file/event evidence contract tested on Windows and Linux | Authenticated cross-process transport, source/replay/version pinning and durable integration monitoring |
| Standalone ForgeQC / PM-Tracker / EZ_Expedite → Axiom | Individual smoke/build tests exist | Some source snapshots and conceptual APIs; **not live synchronized databases** | Define data owner, migrations, scoped adapters and deduplicated events; preserve standalone apps |
| MFGForge / SuperForge Unofficial → Axiom | Historical source line and artifact plans | Axiom is ERP consolidation owner; SuperForge Unofficial isn't a compiled product | Do not create competing ERP writers or promise build assets without jobs |

### Ownership and release boundaries
- **ForgeVault:** released drawing and immutable file/version identity.
- **EZ-FEA:** physical model, mesh and solver claims; a classified mate is not an applied physical constraint.
- **EZ-FAIR:** extracted *candidate* inspection characteristics; no measured values or accepted FAI implied.
- **EZstimate:** cost input, historical price evidence, demand preview and draft PR submission; published indicators are not supplier purchase prices.
- **Axiom:** proposed released estimate/job/quality/ERP system of record; currently only some local intake contracts verified.
- **BEAN Core / Bridge:** observations, provenance, experiment evaluation; a journal event is not autonomous learning or authorization.
- **AIscend, FUN, 64Δ, venvWin:** unrelated or research deployments, not mandatory Axiom runtime dependencies.

## Demo integrity sweep

| Public surface | What the source actually delivers | What it must not imply | Verification path |
| --- | --- | --- | --- |
| [BEAN](https://danieloculus0-bot.github.io/BEAN/) | Static laboratory, original official sprout mascot, public research and evidence links | The website is not a live local Core/Ollama agent | [Main Pages deploy](https://github.com/danieloculus0-bot/BEAN/actions/runs/39512878048), [main Core matrix](https://github.com/danieloculus0-bot/BEAN/actions/runs/39512878059) |
| [AIscend public demo](https://danieloculus0-bot.github.io/BEAN/aiscend.html) | Browser-side read-only simulated account/strategy states | Wallet connection, trades or real account data | [Demo source and tests](https://github.com/danieloculus0-bot/BEAN/blob/main/bean/tests/test_public_aiscend_demo.py) |
| [EZ-FEA Browser Lab](https://danieloculus0-bot.github.io/EZ-FEA/) | Educational beam solver, CAD *preview* and separately verified archived 3D frame evidence | Arbitrary uploaded CAD is not being solved in browser | [Native solver smoke](https://github.com/danieloculus0-bot/EZ-FEA/actions/runs/39510843388), [Pages workflow](https://github.com/danieloculus0-bot/EZ-FEA/blob/main/.github/workflows/pages.yml) |
| [EZ-FEA Joint Matrix](https://danieloculus0-bot.github.io/EZ-FEA/joint-matrix.html) | Editable sample/imported geometry candidates with source faces and no default joint physics | Choosing Welded does not impose verified weld stiffness/connection physics | [Source](https://github.com/danieloculus0-bot/EZ-FEA/blob/main/web/joint-matrix.html) |
| [EZstimate demo](https://danieloculus0-bot.github.io/EZstimate/) | Synthetic RFQ, selectable-text PDF/CSV/TXT extraction and browser-only quote calculation | Not local SQLite pricing, BLS/EIA refresh, BEAN Core, purchasing dispatch or native ERP | [Pages deploy](https://github.com/danieloculus0-bot/EZstimate/actions/runs/39513290745), [source](https://github.com/danieloculus0-bot/EZstimate/blob/main/web/demo.html) |
| [Emperor Gauntlet](https://danieloculus0-bot.github.io/FUN/) | Standalone browser arcade game | Not suite-native manufacturing intelligence; mobile touch still needs device validation | [Pages deploy](https://github.com/danieloculus0-bot/FUN/actions/runs/39504075787) |

**Demo audit limit:** Direct hosted GitHub Pages fetches were unavailable from this audit environment. Descriptions are based on inspected published site source and GitHub Pages job receipts, *not* a fresh visual/mobile interaction pass. No fabricated "demo fully tested on a phone" claims.

## README/CI reconciliation completed in this audit

- **Portfolio:** indexed **16** owned repositories in [CURRENT_PORTFOLIO.md](CURRENT_PORTFOLIO.md), added EZstimate and purchasing, and separated independent products from Axiom.
- **BEAN stable versus experiment:** its **main** full Core CI and Pages both passed. The separate Lab026/adaptive Bridge PR failed importing `ezbean` in the experimental test matrix; see [the PR failure](https://github.com/danieloculus0-bot/BEAN/actions/runs/39515571850). This must not be misreported as mainline Core failure.
- **venvWin:** main's preflight/test README-contract failures were reproduced; restored the portable release/boot criteria on the root README without claiming a bootable ISO. [Main tests](https://github.com/danieloculus0-bot/venvWin/actions/runs/39516239383), [preflight](https://github.com/danieloculus0-bot/venvWin/actions/runs/39516239457) and [branding](https://github.com/danieloculus0-bot/venvWin/actions/runs/39516239415) then passed.
- **Axiom connector freshness:** the local quote wiring job had checked out EZstimate commit `cfba9b40f61e` (before the recent pricing and procurement additions). Re-pinned it to independently tested current EZstimate `bf7502c321ca`; cross-app CI is required on that revision. This verifies backward compatibility of the quote path, **not** the new procurement-to-Axiom path.
- **SuperForge Unofficial:** has historical Actions failures, but no verified recent main-line release. Do not treat it as another installed ERP.

## Build-preparation acceptance gates (priority order)

1. **One actual job, complete traceability:** released ForgeVault drawing hash/revision → EZ-FAIR review required → EZ-FEA evidence if applicable (mechanics separately validated) → EZstimate draft → Axiom quote intake, with live user-level check on the target OS.
2. **Procurement write contract:** approved canonical PR → a real ERP native staging/import adapter; return an ERP-assigned requisition reference, reconcile idempotency/retries and test offline export first. Request approval and ERP submission identities must be authenticated before general shop-network deployment.
3. **Material/price unit normalization:** distinguish purchased sheets/length/weight, manufacturing consumed quantities, scrap/yield and BOM; do not auto-copy price-per-sheet into price-per-part.
4. **BEAN Core reliability:** validate concrete installed local Core + Bridge paths on the same machine; journal evidence must have source/date/version and tested restart continuity. Autonomous agent milestones must pass separate holdout tests before claims.
5. **Demos and packaged apps:** verify static Pages links, test Windows installer startup and one target mobile viewport; do not confuse CI syntax/deploy checks with real interactive device tests.
6. **One launch surface:** unified Gothic Lime navigation/session/workspace with cross-module deep links. Keep stable local APIs, measure bottlenecks before any Python-to-native rewrite.

**Release criterion:** a coherent app can demonstrate the end-to-end **verified subset** with source receipts, visible pending reviews, recoverable errors and no unauthorized procurement/order writes. Unknown, unsupported and offline connections stay visibly unknown; they are never shown as green.
