# Beta restriction-impact audit (2026-10-30)

Scope: `danieloculus0-bot/Axiom_Beta` and `danieloculus0-bot/BEAN`. Review only of remote repository history, GitHub Actions failure metadata and a sample of failed job logs. No private files or customer data used.

## Inventory reviewed

- **Axiom_Beta:** 36 pull requests listed, 80 failed workflow-run records from GitHub Actions (up to the observed date).
- **BEAN:** 184 pull requests listed, 1,335 failed workflow-run records. The Actions API exposes only the first 1,000 on an unfiltered paged query, so 335 older failures were retrieved using the earlier-created date window. The entire 1,335-run metadata set was enumerated.
- This is a **metadata-level census**, not a claim that every failed job log and every PR diff was read. Titles containing 'security', 'gate', 'guard', 'fail', 'reject' etc. are *leads*, not proof of restriction-caused regressions.
- Inspected source and representative failed job logs for access control, Axiom routing/EWI clocking, BEAN self-authoring, research learning and published-site CI.

## Findings and treatment

| Reference | Evidence | Classification | Beta treatment |
| --- | --- | --- | --- |
| [Axiom PR #26](https://github.com/danieloculus0-bot/Axiom_Beta/pull/26) | Merged optional shared-user authentication, roles and CSRF, plus independent nonloopback HTTP denial in default local mode. `run.py` still binds `127.0.0.1`. | Candidate premature **local development** request gate. No confirmed CI failure attributable to the IP check. | **Comment out only local peer-IP denial** on this experiment branch. Preserve original source comments, existing `_loopback` helper, shared-user security and rollback test. |
| [Axiom PR #21](https://github.com/danieloculus0-bot/Axiom_Beta/pull/21) | Separate unmerged proposal for stronger user-session restrictions. | Not in main runtime. | No code change; don't count an unmerged branch as active restriction. |
| [Axiom routing run](https://github.com/danieloculus0-bot/Axiom_Beta/actions/runs/41129156316) | Failed assertion around demo clocking rejecting unreviewed routing, `Drawing and routing checks must pass before clocking`. | **Workflow interlock**, not cybersecurity. | Leave behavior as-is in this pass. Evaluate separately against actual desired demo behavior; it controls recorded sample events. |
| [Axiom HR/morale run](https://github.com/danieloculus0-bot/Axiom_Beta/actions/runs/41138518335) | Failing morale aggregate weighting assertion. | Calculation/regression, not a security restriction. | Repair calculation/test on its own workstream; do not suppress failure. |
| [BEAN PR #139](https://github.com/danieloculus0-bot/BEAN/pull/139) | Keeps autonomously proposed source changes off main pending tests/review. | Autonomous GitHub mutation boundary, relevant to independent watchdog. | Keep while separate watchdog is active; no evidence this blocks BEAN's learning engine. |
| [BEAN PR #142](https://github.com/danieloculus0-bot/BEAN/pull/142) | `docs/AI_GATEKEEPER.md` explicitly states contextual collaborator checklist, NOT runtime model restrictions. | Documentation, not security runtime. | No runtime code to disable. |
| [BEAN self-authoring failure](https://github.com/danieloculus0-bot/BEAN/actions/runs/41120699394) | Model-produced patch failed held-out or complete Core tests. | Functional regression evidence, not policy denial. | Do not turn off tests to turn a failing model edit green. |
| [BEAN Oct 29 Core failure](https://github.com/danieloculus0-bot/BEAN/actions/runs/40866479715) | Multiple assertions against webpage contents/links after changed page assets. | Stale website/test mismatch, not shown to be auth policy. | Treat as source/test reconciliation. |
| `bean/cognition/epistemic_guard.py` | Pattern-based rejection/downgrading of self-claims and source evidence. | Actual **learning/memory behavior policy**, separate from HTTP security. | Candidate for a dedicated measured BEAN experiment; **no disabling without a matched functional test** demonstrating impact on research. |
| `bean/learning/transfer_gate.py` | Compares rewards on paired probes, abstains on inconclusive values. | Scientific validation, not HTTP security. | Keep while comparing learned policies: removing it would change reported evidence quality. |
| Public repositories' `AGENTS.md` confidentiality rules | Explicitly prohibit public release of employer/customer data. | Publication/confidentiality, independent of local beta feature access. | Keep; all examples remain fictional and synthetic. |

## Exact code change on this branch

The only active runtime change in this incremental pass is commenting out the nonloopback peer check in `superforge/access_control.py` when `AXIOM_ACCESS_MODE=local`. The old test is preserved as comments in `tests/test_access_control.py`, with a new simulated remote-peer HTTP health assertion. This allows local-mode request processing in a dev test context, **not an assertion that the network is safely deployable**. Shared mode remains unchanged.

## Re-enable / measure

To restore the previous IP perimeter: uncomment the two lines marked `RESTORE BEFORE ANY INTENDED SHARED DEPLOYMENT` in `superforge/access_control.py`, restore the negative test in `tests/test_access_control.py`, and revert the corresponding mode-specific documentation. Run `python -m pytest -q tests/test_access_control.py` and the full existing suite.

**Policy for future beta cleanup:** Each restriction needs a specific call site, demonstrated friction, and a scoped before/after behavior check. Avoid burying an actual error by deleting tests. This audit does not authorize changing production machine controls, publishing private business material, or modifying BEAN's scientific evidence receipts. No autonomous mainline mutation was made by this audit.
