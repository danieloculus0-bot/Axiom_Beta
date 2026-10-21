# Supplier Price & Delivery Intelligence

The local Axiom purchasing engine now keeps append-only supplier quotation and delivery evidence. The module makes **purchase suggestions**, never creates/sends supplier orders by itself.

## Price catalog and ranking

Each source-backed quotation preserves the supplier, inventory item, exact Axiom stocking unit, USD price per unit (Decimal as text), minimum order quantity, pack multiple, quoted lead days (if known), quote date, expiry and source reference. New quotations append history without replacing older receipts. An expired superseding quote cannot resurrect an older price.

The Supplier Intelligence dashboard is available at `/purchasing/suppliers` and linked from `/purchasing`. Its first view shows min/max restock candidates and also compares existing draft or approved local PR quantities, without changing any requisition.

Recommendations are ranked first by a dated ability to meet the documented need, then estimated extended cost using MOQ and multiples. The ETA uses the worse of the current quote lead time and available median completed-line lead time. Missing quote and actual lead data is **UNKNOWN**, never treated as zero days. Where there is no need date, ranking compares eligible quote totals and explicitly declines to claim a guaranteed arrival date.

Delivery history is displayed as a sample count. Less than three original-promise completions is labeled *insufficient samples*. A quoted ETA remains an estimate, not a supplier commitment. Price history here represents documented supplier offers, **not reconciled invoice costs**.

## Promised versus actual delivery

When an approved local PR is first attached to a purchase order line, Axiom captures immutable evidence of:

- The original supplier from the PO header (when assigned) and original PO placement date
- The original promised delivery date, if the PO header has one

Further confirmed promise dates append versioned entries on that PO line. Inventory forecast uses the latest recorded line promise for expected inbound; historical supplier punctuality compares the **original promise** with final arrival date, so a late supplier does not erase a miss by revising the promise.

The receiving form includes the physical receipt date. Each successful receipt records the date within the same transaction as the inventory increment, and an identical idempotency key cannot be reused with different quantity/PO line/date. An entry dated in the future, or before an existing PO order date, is rejected. If an old receipt has no physical date record, its date is not invented.

Only **completely received lines** whose entire quantity has recorded arrival dates qualify for actual delivery metrics. `actual_received_on` is the final arrival date among partial receipts. On-time % uses the first recorded supplier promise; median actual lead days uses the original PO placement date. Missing dates are excluded rather than silently scored as on time.

Original supplier and placement date are snapshotted to prevent later edits to the legacy freeform PO header from rewriting attribution. Existing legacy PO lines that predate this evidence schema are not automatically backfilled.

## Sample decision

A $12 quoted supplier requiring fourteen days may be ranked behind a $16 supplier quoting three days when a job needs the item in five days. Both prices, date calculations, sample sizes and supplier source references remain reviewable. Neither ranked option produces an outbound PO.

## Known gaps

Still needs validated actual receipt benchmarks from shop usage, real supplier quote sources, integrated invoice cost/three-way matching, supplier-specific freight/currency/tax, location and stock-bin tracking, and ERP/supplier acknowledgement. Approver identity/security and network deployment remain a separate later phase; this functionality is local only.

## Validation

Tests cover quote append-only history, superseding expiry, unit and price validity, MOQ and pack rounding, on-time versus late quote rank, partial/full receipt dates, original and changed promises, PO header mutation resistance, idempotency, persistence and browser endpoint operation. Run `python -m pytest -q` on the repository and inspect Windows/Linux package CI before deploying.
