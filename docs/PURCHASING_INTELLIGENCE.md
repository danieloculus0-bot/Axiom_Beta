# Axiom Purchasing Intelligence: v1 local engine

This implementation changes actual Axiom SQLite records, not the public browser lab. It does not automatically create vendor orders, contact suppliers, or claim a third-party ERP accepted a requisition.

## Workbench

The /purchasing view is linked from the sidebar, PO tracker, EZ Methods, and job evidence.

- Configure one explicit stocking unit per stock item (ea, sheet, lb, kg, ft, m), min/max, lead days and ordering multiple. It will not convert lb to sheet or sheet to ea.
- Set absolute job reservations; consumption first uses that job's reserved stock and then free stock. Consumption changes on-hand and, where used, allocation. Stable movement keys make repeat posts idempotent.
- Map an actual EZ Methods material or purchased-part dependency to a stock item and a reviewed stocking-unit quantity. No description guessing. Job consumption reduces the remaining linked method requirement.
- Compute suggestions using actual stock, allocation, outstanding linked PO lines, remaining linked method requirements, past 30-day consumption and lead time. Only expected receipts within lead time count as projected on-time inbound.
- Create draft local requisitions, review them, attach an approved request to an existing PO, receive partial or full quantities, and update Axiom stock and transaction history atomically.
- Import an EZstimate source PR by pasting its canonical stored request or dispatch envelope. All material item codes, units and jobs must match. SHA-256 integrity, all-or-nothing import and idempotent request IDs are checked. Imported source approval does not become an Axiom approval.

## Forecast equations

Available = on_hand - allocated

On_order = sum unreceived quantities of linked active PO lines

On_time_inbound = confirmed expected-date inbound between today and today + lead_days

Unreserved_method_need = remaining linked requirements minus outstanding reservations, grouped by job

Daily_use = consumption posted in the last 30 days / 30

Stock_position = available + on_order - unreserved_method_need

Projected_stock = available + on_time_inbound - unreserved_method_need - daily_use * lead_days

For projected_stock at or below min, suggested order = ceil(max(0, max - (stock_position - daily_use * lead_days)) / ordering_multiple) * ordering_multiple.

If projected stock is short but total recorded inbound already covers the target, the signal becomes EXPEDITE instead of generating a duplicate purchase suggestion. Unconfigured items show UNCONFIGURED.

These are planning suggestions, not verified supplier commitments. Consumption history and job requirements can overlap future demand patterns, so staff should review forecast signals. Existing methods readiness is not automatically released.

## Integration boundaries

- Axiom inventory: real on-hand, allocated and transaction history.
- Axiom jobs: job reservations and actual job consumption.
- EZ Methods: explicit stock requirement links and consumption-based fulfillment.
- Axiom purchase_orders: existing header, added lines and receiving.
- Axiom Job Passport: job-linked purchasing requisitions and reservations.
- EZstimate: source PR intake into local draft, never ERP acceptance.
- External ERP/supplier: no automatic network delivery, supplier order or acknowledgement.

Legacy freeform PO headers are not sufficient evidence of incoming stock. Only procurement-linked order lines count towards inbound; receipts alone increment on-hand. Existing inventory reorder_point remains unchanged, and unowned legacy allocations are not silently attributed to jobs.

## Tests and next work

Automated Python tests exercise min/max, late inbound, job reservations and consumption, replay-conflict rejection, unit mismatch, PR import atomicity, partial receipts, over-receipt rejection, and restart persistence. The EZstimate cross-repo workflow additionally tests a real persisted EZstimate PR and Axiom intake on Linux/Windows.

The workbench remains local-first, with user-entered actor labels rather than authenticated enterprise approval. Do not publish the Flask port onto a shared shop network.

Later engine iterations can add supplier quote catalogs, reliable lead-day feedback, stock bins and multiwarehouse support, unit conversions, returns, quality quarantine receiving, 3-way matching, and native ERP/vendor delivery with provider acceptance receipts.
