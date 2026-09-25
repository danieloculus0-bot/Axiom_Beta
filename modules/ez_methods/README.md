# EZ Methods

EZ Methods is the SuperForge methods-master-planning module. It turns controlled customer and manufacturing requirements into executable routing methods, then keeps the routing connected to tooling, material, purchasing, inspection, quality, and audit records.

## Core rule

A routing is not ready merely because somebody wrote the steps. It is ready only when the requirements and resources needed by each operation are known and expected to be physically available before that operation is scheduled.

Examples:

- Raw material must be available before the first consuming operation.
- A tap, fixture, gage, program, purchased component, coating, or outside-process slot must be available by the operation need-by date.
- Ordered is not the same thing as ready.
- A promised delivery after the consuming operation's scheduled date is a blocker.
- Missing ownership, missing next action, stale activity, and overdue commitments use EZ Expedite behavior.

## Requirement authority

The planner preserves the Routing & Planning Bible hierarchy:

1. Customer PO / contract
2. Customer drawing and current revision
3. Customer specifications / standards / referenced documents
4. Approved changes, deviations, concessions, or written approvals
5. Controlled internal procedures / work instructions
6. Released routing
7. Informal notes or tribal knowledge

Conflicts stop planning until resolved.

## Inputs

EZ Methods is designed to accept drawings, customer POs, ERP job/order exports, prior routings, NCR/RMA/CAR lessons, supplier status, tooling registries, outside-process requirements, and FAI/PPAP requirements.

The extraction layer reuses and extends EZ FAIR behavior for dimensions, title-block tolerances, ballooning, and GD&T recognition. Extracted items remain reviewable before a routing is released.

## GD&T

The data model supports straightness, flatness, circularity, cylindricity, profile of a line, profile of a surface, angularity, perpendicularity, parallelism, position, circular runout, total runout, legacy concentricity, legacy symmetry, datum reference frames, RFS/MMC/LMC, diameter zones, projected tolerance zones, tangent plane, free state, all-around/all-over controls, basic dimensions, and characteristic-specific inspection methods and gage IDs.

EZ FAIR extraction can seed the characteristic. EZ Methods adds process ownership: what operation creates the feature, when it must be verified, how it is verified, and which resource is required.

## Purchasing / EZ Expedite integration

Every dependency can create or link to a PURCHASING / SHORTAGE occurrence containing job, part, routing operation, supplier, supplier PN, internal Tool ID, PO number, owner, next action, need-by date, promised date, required/ordered/received quantity, readiness state, and full activity history.

The key comparison is promised delivery date versus operation need-by date, not merely promised delivery date versus final customer due date. That catches shortages before the job reaches the machine.

## Canonical method example

Using Fastenal PN 12345678 tap, tap (7) 5/16-18 holes as shown on DWG 33344455 Sht 2.

That statement is stored as structured data:

- operation: Drill / Tap
- feature count: 7
- thread: 5/16-18
- supplier: Fastenal
- supplier PN: 12345678
- internal Tool ID: prompted when desired or required
- source: DWG 33344455, Sheet 2
- tool availability: tracked
- need-by date: tied to the machining operation
- purchasing occurrence: generated when availability is not confirmed
- inspection requirement: linked to the source characteristic
- audit events: extraction, review, release, purchasing trigger, status changes, and completion

## Routing lifecycle

1. Intake drawing, PO, ERP/job, and prior-plan data.
2. Extract key requirements and source locations.
3. Review and approve extracted requirements.
4. Build sequential operations.
5. Bind requirements to the operation that creates or verifies them.
6. Ask for tool, fixture, gage, or program IDs when required.
7. Create dependencies and operation-level need-by dates.
8. Check inventory and known availability.
9. Trigger purchasing/expedite records for gaps.
10. Add inspection gates, FAI/PPAP controls, and Final Inspect.
11. Run readiness gate.
12. Release routing.
13. Record execution evidence by operation.
14. Feed NCR/RMA/CAR lessons back into the master routing.
15. Preserve every state change in the shared SuperForge audit ledger.

## SuperForge integration

EZ Methods participates in the shared context router. Right-click actions can expose Open EZ Methods, Check Operation Readiness, Open Purchasing / Expedite, Supplier History, Open FAI / Inspection Characteristic, Gage / Tool History, and View Audit Trail.

The module is intentionally deterministic for transaction decisions. Learning or AI assistance may suggest methods, likely tooling, inspection points, or lessons learned, but it does not silently alter released manufacturing requirements.
