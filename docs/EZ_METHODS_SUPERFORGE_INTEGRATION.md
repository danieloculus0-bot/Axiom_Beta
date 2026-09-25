# EZ Methods / SuperForge integration

## Purpose

EZ Methods is the planning brain between customer requirements and execution.

It connects drawings and PO requirements, routing and methods, material and tooling readiness, purchasing and EZ Expedite, FAI/inspection/GD&T, NCR/RMA/CAR lessons, JobBOSS2/ERP references, the shared audit ledger, and SuperForge context menus.

## Event contract

Every meaningful action emits a shared event. Minimum events include:

- METHOD_REQUIREMENT_EXTRACTED
- METHOD_REQUIREMENT_REVIEWED
- METHOD_OPERATION_CREATED
- METHOD_DEPENDENCY_CREATED
- METHOD_DEPENDENCY_BLOCKED
- PURCHASE_REQUEST_TRIGGERED
- PURCHASE_COMMITMENT_CHANGED
- METHOD_OPERATION_READY
- METHOD_ROUTING_RELEASED
- METHOD_OPERATION_COMPLETED
- METHOD_INSPECTION_RECORDED
- METHOD_NCR_LINKED
- METHOD_ROUTE_REVISED

Each event contains entity IDs, actor, timestamp, source reference, payload, previous hash, and event hash.

## Logic connections

- Drawing or PO requirement creates a controlled requirement record.
- Requirement binds to one or more routing operations.
- Routing operation creates resource dependencies.
- Resource dependency checks available quantity and committed dates.
- Missing or late resource creates or links an EZ Expedite purchasing occurrence.
- Purchasing updates immediately recompute operation readiness.
- GD&T and dimensional characteristics create inspection requirements.
- FAI/PPAP characteristics link to the operation that creates them and the operation that verifies them.
- NCR/RMA/CAR findings can flag the master routing for review.
- Released-route changes create revision events rather than silent overwrite.
- Final Inspect remains a discrete controlled operation.

## AI boundary

AI may assist with extraction, requirement grouping, suggested routing sequence, likely tooling, risk prompts, and lessons-learned recall.

AI does not get final authority to invent or silently change tolerances, material specifications, customer requirements, GD&T controls, approved sources, inspection acceptance criteria, or released process changes. Those remain deterministic and source-traceable.
