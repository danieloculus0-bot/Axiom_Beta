# EZ-Ladder + Axiom Maintenance: first X-axis diagnostic experiment

**Status:** synthetic, review-only experiment, November 1, 2026. No live PLC, equipment, BEAN inference service, EWI, sensor interface, or safety authorization.

## Reused code

- `web/erp/pm.mjs`: canonical fictional PM machine ID, validation and existing `requestMaintenance` operation. The diagnosis never creates a parallel equipment database.
- `web/erp/pm-work-center-link.mjs`: reviewed mapping between fictional machines and work centers. This experiment starts with an existing PM machine only and does not guess a work-center relationship.
- `web/erp/routing-bean-adapter.mjs`: precedent for review-only, source-linked BEAN proposal boundaries. Our `beanHandoff` object is an **offline candidate envelope**, not a BEAN Core API call or an inference result.
- `web/erp/axis-diagnostic.mjs`: new minimal read-only diagnostic classification from explicit fictional inputs. Its two displayed Boolean contacts are illustrative rung traces, not a PLC ladder parser.
- `web/erp/axis-diagnostic.test.mjs`: six synthetic regression tests, including unknown-feedback abstention and existing PM request handoff.

## Experiment

Run `node web/erp/axis-diagnostic-demo.mjs` at the Axiom repository root. It creates an existing `DEMO-M-001` PM machine state, submits this **invented** snapshot, evaluates simple rung conditions and requests a fictional maintenance follow-up only after an explicit demo review:

| Observed signal | Value |
| --- | --- |
| Move requested | true |
| E-stop healthy / guard closed | true / true |
| PLC motion output / step pulses | true / true |
| Drive ready / fault | true / false |
| Supply voltage | 24 V (fictional) |
| Motor current | 2.1 A (fictional) |
| Shaft rotation / X-axis displacement | false / 0 mm |

**Expected result:** `STALL_OR_BINDING`. Candidate explanations: mechanical binding, insufficient drive torque/tuning, or motor defect. A bad motor is **not proven** by this evidence. More measured feedback is needed. The hypothetical reviewed result becomes one existing Axiom `DEMO-MWO-` maintenance request in copied PM state, leaving the original state untouched.

Control comparisons test open guards, missing PLC output, drive fault, missing pulses, near-zero motor current, rotating shaft without axis motion, and missing instrumentation. Each should report a different category, not falsely conclude a broken stepper.

## Constraints

All public examples must remain fictional. This never bypasses safety circuits, emits motion commands, writes to a controller or claims an inspected physical machine. A production-grade solution needs validated vendor-specific adapters, signal provenance and timestamps, trustworthy state snapshots, independent safety controls, and equipment-specific diagnostic knowledge. BEAN's eventual role is to compare evidence with **previously observed cases**, retaining cited receipts and treating hypotheses as hypotheses.

## Future connection

Once reviewed, the Axiom Maintenance UI could display signal state, rung trace, confidence limits, checks and a repair-request draft. EZ-Ladder can own vendor-independent ladder parsing and adapter contracts in its separate repo. The integration boundary should use existing Axiom asset identity and BEAN's existing event-memory system; do not create competing record stores. No changes to the Axiom production-facing navigation or equipment control are made by this experiment.
