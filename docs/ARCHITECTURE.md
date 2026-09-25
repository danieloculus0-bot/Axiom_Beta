# Unified Architecture

```text
                         +----------------------+
                         |   SuperForge Shell   |
                         | dark/light + context |
                         +----------+-----------+
                                    |
                          universal context router
                                    |
      +-----------+-----------+-----+-----+-----------+-----------+
      |           |           |           |           |           |
    Jobs         POs      Inventory    Quality       PM        Vault/FAI
      |           |           |           |           |           |
      +-----------+-----------+-----+-----+-----------+-----------+
                                    |
                              domain event bus
                                    |
                     +--------------+--------------+
                     |                             |
                event ledger                  audit journal
             SQLite relational              JSONL hash chain
                     |                             |
                     +--------------+--------------+
                                    |
                         workflow/action engine
                                    |
             +----------------------+----------------------+
             |                      |                      |
      Leadership / Pulse        Automation            ERP adapters
   morale / rewards / training   event rules     flatfile / REST / SQL
             |                      |                      |
             +----------------------+----------------------+
                                    |
                              BEAN learning
                         observations / proposals
                                    |
                              human review gate
```

## Transaction boundary

Authoritative records and event routing are deterministic. Learning is advisory.

## Audit boundary

A business mutation is not considered complete until its journal write succeeds. Derived actions retain the originating event/correlation identity.

## Integration boundary

External systems never become hidden second sources of truth. Every import has a sync run. Every external row has a durable external reference. Every outbound write is queued/reconciled and receives a receipt or retry state.

## Context boundary

Every module can accept `context_type` and `context_id`. Direct relationships are used to filter the destination when possible. No blank re-search should be required for common cross-module navigation.


## Leadership boundary

Company Pulse uses aggregate operating and workforce-health signals to direct leadership attention. Recognition, training and reward transactions are separate auditable records.

## Automation boundary

Configurable rules may create workflow actions from domain events. They do not bypass the controlled event logic or grant BEAN permission to rewrite production behavior.
