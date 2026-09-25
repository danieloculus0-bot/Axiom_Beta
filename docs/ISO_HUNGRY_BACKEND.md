# ISO-Hungry Reporting-to-Pay Backend

ISO-Hungry is implemented inside SuperForge as a backend reporting and compensation bridge. It does not need a separate UI to work.

## Event flow

1. A module records a verified report event through the shared SuperForge event bus.
2. Existing recognition rules decide whether that event earns recognition points.
3. The normal reward ledger records the approved recognition event.
4. ISO-Hungry listens for \`recognition.awarded\`.
5. A cash policy converts the approved recognition into a payable earning.
6. Payable earnings remain pending by default until a reviewer approves them.
7. Approved earnings are frozen into a pay-period batch.
8. An approved batch exports deterministic payroll CSV data.
9. The CSV content receives a SHA-256 receipt.
10. When the external payroll system confirms payment, the batch and its earnings are marked paid with the external reference.

This keeps reporting, recognition, and cash compensation separate while preserving one traceable chain.

## Core tables

- \`iso_hungry_pay_profiles\`: maps a SuperForge reward account to internal employee/payroll references and a pay group.
- \`iso_hungry_cash_policies\`: defines category/source matching, dollars per point or fixed amounts, earning code, currency, event caps, rolling 30-day caps, and approval behavior.
- \`iso_hungry_earnings\`: one immutable payable record per profile, policy, and reward event.
- \`iso_hungry_pay_batches\`: pay-period batch header with approval, export hash, and payment confirmation.
- \`iso_hungry_pay_batch_items\`: snapshots payroll-facing employee references and earning details so later profile edits do not rewrite an already-created batch.
- \`iso_hungry_exceptions\`: catches payable events that cannot proceed because a pay profile is missing or on hold.

## Duplicate and gaming controls

A single reward event cannot create the same payable earning twice because the database enforces a unique profile, policy, reward-event key.

Cash policies default to human approval. Auto-approved policies can be configured, but rolling limits are checked before automatic approval.

A report does not create money directly. The chain is:

\`reported event -> recognition rule -> reward event -> cash policy -> payable earning -> approval -> pay batch -> export -> paid confirmation\`

The reporting event, reward event, payable earning, batch creation, approval, export, and payment confirmation all leave audit receipts.

## Payroll export

\`export_pay_batch_csv()\` returns a deterministic CSV containing:

- batch key and pay period
- employee reference
- payroll reference
- pay group
- earning code
- currency
- amount
- earning ID
- reward event ID
- original source event ID
- category and reason

SuperForge records a SHA-256 hash of the export. If the content changes after export, the backend refuses to treat it as the same recorded payroll file.

## Payment boundary

ISO-Hungry deliberately stops at payroll-ready export and external payment confirmation. It does not move money itself. The payroll system remains responsible for withholding, taxation, wage rules, final payment execution, and its own approvals.

## Minimal backend example

\`\`\`python
account_id = create_reward_account("CARD-17", display_name="Operator 17")

upsert_pay_profile(
    account_id,
    employee_ref="EMP-17",
    payroll_ref="PR-17",
    pay_group="WEEKLY",
)

create_reward_rule({
    "name": "Verified quality event",
    "event_type": "report.quality_win",
    "source_module": "reporting",
    "account_payload_key": "reward_account_id",
    "payload_key": "verified",
    "operator": "truthy",
    "category": "quality",
    "points": "5",
    "requires_approval": "0",
})

create_cash_policy({
    "name": "Quality bonus",
    "reward_category": "quality",
    "source_module": "reporting",
    "dollars_per_point": "1.00",
    "earning_code": "ISOH_BONUS",
    "rolling_30d_limit": "100",
    "requires_approval": "1",
})

record_reported_event(
    "report.quality_win",
    reward_account_id=account_id,
    source_module="reporting",
    entity_type="inspection",
    entity_id="INSP-4402",
    actor="supervisor",
    payload={"verified": True},
)
\`\`\`

The resulting cash earning is pending until approved. After approval it can be included in a payroll batch and exported.
