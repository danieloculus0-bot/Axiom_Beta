# Axiom as a Learning ERP

Axiom is not intended to win by recreating every screen in a legacy ERP. Its differentiation is the operating model between the data and the decision.

Traditional ERP systems are primarily transaction systems. They are excellent at storing orders, jobs, inventory, labor, quality records, accounting records and master data. Axiom keeps those capabilities, but its architecture adds a common event spine, cross-module context, organizational hierarchy, decision protocols, human-governed recommendations, delegated actions, outcome capture and supervised learning.

## Core loop

```text
Input anything
    -> normalize entities and events
    -> connect operational context
    -> apply deterministic business / decision protocols
    -> rank the few signals that matter
    -> recommend a controlled action
    -> resolve the responsible role / person
    -> human accepts, changes or dismisses
    -> create an auditable workflow action
    -> capture the outcome
    -> feed the outcome into supervised learning
    -> propose better future rules without silently rewriting production logic
```

## 1. Input anything

Axiom should accept information through approved interfaces such as:

- ERP report drops
- CSV / JSON
- Excel workbooks
- REST APIs
- approved SQL / report views
- web forms
- NCR / RMA web intake
- controlled documents and drawings
- FAI / inspection evidence
- payroll and finance inputs
- purchasing and inventory records
- maintenance records
- training / recognition events
- future approved connectors

The source format is not the internal operating model. Inputs are normalized into canonical entities, domain events and durable external references.

## 2. One context model

Axiom should be able to connect a signal to the surrounding operating context:

- customer
- supplier
- part / revision
- job / work order
- purchase order
- material / inventory
- operation / routing
- machine
- drawing / specification
- quality record
- FAI / PPAP
- employee / role
- payroll run
- accounting journal
- organizational unit
- responsible role
- workflow action

This allows the same fact to be interpreted differently depending on what it threatens.

## 3. Organizational intelligence

The organization is part of the data model.

Axiom stores:

- organizational units
- roles
- reporting lines
- authority levels
- people
- role assignments
- primary role holders

A decision protocol can therefore target a role such as `quality_manager` or `operations_manager` rather than hard-coding a person's email address into business logic.

When the person holding that role changes, routing changes without rewriting the process.

## 4. Decision protocols

A decision protocol describes what an event means operationally.

A protocol can define:

- source event type
- optional source module
- signal type
- target module
- target organizational role
- priority
- expected action
- impact baseline
- urgency baseline
- confidence floor
- escalation window

Protocols are deterministic and auditable. They provide the governed boundary between raw events and executive recommendations.

## 5. True Pareto focus

Axiom should not show leadership every open record and call that intelligence.

Executive Intelligence ranks open decision-protocol recommendations by weighted impact and presents the smallest set of signals whose combined score represents at least 80 percent of current executive impact.

This is not a fixed rule that simply displays 20 percent of rows.

The Pareto view answers:

- What few things explain most of the current risk?
- What role owns each decision?
- What is the recommended next action?
- Which recommendation has already become assigned work?
- What happened after we acted?

## 6. Recommendations are not autonomous commands

Axiom recommendations remain human-governed.

The executive layer reuses the canonical `module_suggestions` queue.

An accepted recommendation creates an ordinary `workflow_action` with:

- source event
- target module
- entity context
- assignee
- status
- timestamps
- audit receipts

Dismissal and acceptance both remain auditable.

Controlled manufacturing, quality, payroll and accounting logic is not silently changed by learning.

## 7. Learning from outcomes

When a recommendation has an outcome, that result becomes a supervised learning observation.

Useful outcome labels include:

- recommendation accepted / dismissed
- recovery successful / unsuccessful
- recurrence prevented / repeated
- delivery recovered / missed
- cost avoided / incurred
- supplier recovery worked / failed
- training correlated with better later outcomes
- corrective action effective / ineffective

BEAN-style learning can compare these outcomes and propose changes to:

- thresholds
- routing
- protocol language
- escalation timing
- data requirements
- review steps

Those proposals remain proposal-only until a human review grants sandbox or human-execution permission.

## 8. ERP versus operating intelligence

Axiom still needs reliable ERP fundamentals: jobs, purchasing, inventory, payroll, accounting, quality, documents, maintenance, planning and integration.

Its differentiator is not that established ERP products are incapable of storing the same raw information.

The differentiator is that Axiom is designed around:

- one shared context model
- event-driven cross-module behavior
- organizational hierarchy
- explicit decision protocols
- Pareto executive focus
- recommendations that become auditable work
- outcome feedback
- supervised learning
- portable input adapters

That makes Axiom a transaction system plus an operating intelligence system.

## 9. Product rule

A simple rule should remain true as Axiom grows:

> ERP records what happened. Axiom should understand what matters next.

That statement is an architectural target, not a claim that Axiom already matches the deployment scale, ecosystem, regulatory coverage or decades of production hardening of established enterprise platforms.
