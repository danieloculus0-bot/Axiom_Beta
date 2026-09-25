# Leadership, Company Pulse, Recognition, and Automation

SuperForge should help leadership see operating problems early, assign work clearly, recognize good performance, and verify that actions were completed.

## Company Pulse

The Leadership / Company Pulse module combines cross-functional operating signals with an aggregate workforce-health pulse.

Current aggregate inputs include scheduled versus present headcount, overtime, heavy-overtime count, PTO pressure, absence clusters, turnover, staffing shortages, and an aggregate quality-risk signal.

Pulse data is recorded by department and period. The score is a bounded attention heuristic for leadership, not an individual performance score.

High aggregate risk emits a normal SuperForge domain event. The event spine can create leadership review work and send the signal to BEAN for supervised trend comparison against quality, delivery, workload, and other operating outcomes.

## Recognition / ISO-Hungry direction

Recognition is separate from risk reporting.

Reward accounts support an external vending or canteen account reference so SuperForge can integrate with existing vendors rather than owning vending infrastructure.

Credits can recognize throughput, accuracy, first-pass quality, compliance, training, kaizen, safety, and positive recognition.

Awards are positive credits. Redemption is a separate ledger entry. Every award and redemption emits an event and audit receipt.

## Training

Training requirements can define a key, title, department or role, recurrence interval, recognition points, and notes.

A verified completion emits a training event. When recognition points are configured and a reward account is linked, those points are credited through the audited reward ledger.

## Leadership accountability

The Company Pulse page surfaces open workflow actions, overdue actions, unassigned actions, open quality cases, late or at-risk purchase orders, blocked EZ Methods dependencies, and recognition activity.

Workflow actions can be completed from the leadership queue and closure is recorded in the audit journal.

## Deterministic automation

The Automation module extends the hard-coded event logic with configurable rules.

Rules can match event type, source module, an optional payload field, an operator, and a comparison value. Matches create normal assigned and due-dated workflow actions.

Each rule executes at most once for a given source event. The execution receipt stores the source event ID and generated workflow action.

SuperForge keeps three concepts separate:

1. Deterministic operating logic for required process behavior.
2. Configurable automation for routing and accountability.
3. BEAN learning for evidence-backed proposals that remain human reviewed.

That separation lets the system automate aggressively without allowing learned behavior to silently rewrite controlled production rules.
