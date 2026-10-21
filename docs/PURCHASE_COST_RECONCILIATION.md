# Axiom: actual purchase-cost reconciliation

The local engine uses the **same Axiom SQLite purchase orders, procurement lines, supplier history, receiving movements, job transactions and inventory items**. It does not use the public browser lab or a second disconnected stock balance.

## Reconciliation workflow

1. Axiom purchasing creates a reviewed requisition and links it to a PO line. Stock on order is not stock received.
2. Record the actual **buyer-agreed PO unit price** with its document/confirmation reference. A historical supplier quotation alone is not an agreed price. Optional quote IDs must match supplier, material and stocking unit, and the amount must agree exactly.
3. Record the actual supplier invoice number and date against one or more PO lines. Document USD material price, quantity, exact stock unit, freight, other landed charges, and tax. A source reference is required; optional SHA-256 identifies the backing invoice file. The invoice is immutable and source-number idempotent.
4. Axiom matches billed quantity against the sum of recorded billed quantities, PO ordered quantity and physically received quantity. It also matches invoice unit and agreed PO unit price. Invoice amounts never create physical inventory receipts.
5. Invoice lines enter one of these states: **HOLD** for over-ordered/over-received quantity, missing PO price or unit mismatch; **VARIANCE_REVIEW** for price differences or extra landed charges; **RECONCILED** only when full evidence matches or a non-blocking variance receives a documented local review. Reconciling is not AP payment.
6. Associate recorded job consumption with a reconciled invoice line to attribute **documented material cost**. The cost equals associated quantity times actual invoiced landed cost per unit. The association is capped by both the posted consumption quantity and available invoiced quantity. It is not proof of physical lot traceability.

## Math

Material price variance = (invoice unit price - agreed PO unit price) x invoice line billed quantity.

Invoiced material amount = invoice unit price x billed quantity.

Landed amount = invoiced material amount + freight + other charges + tax.

Actual landed unit cost = landed amount / billed quantity.

Job consumption assigned cost = manually associated job-consumption quantity x actual landed unit cost.

Currency is fixed USD and quantities are in the shared inventory stocking unit. Money is calculated with decimal arithmetic, preserving fractional unit prices; invoice material and landed totals are presented to two decimal places.

## Cross-module visibility

- Purchasing workbench: `/purchasing`
- Supplier quoted price and delivery history: `/purchasing/suppliers`
- Invoice, receipt, price and job material-cost workbench: `/purchasing/costs`
- Review-required actual cost observations for EZstimate: `/purchasing/costs/feedback.json` using schema `axiom.actual_material_cost_feedback.v1`.
- Job Passport: `/jobs/<job ID>/passport` displays job-linked evidence-backed **partial** material consumption cost. It never converts an unrelated part-linked estimate into job cost.

Price feedback includes supplier, stocking unit, invoice references, original agreed PO price, actual material unit price and landed unit cost; **EZstimate does not automatically adopt or overwrite any price memory**. A review/import adapter is needed for that subsequent step.

## Constraints and exceptions

- This is **not** a general ledger, accounts payable, invoice-payment gateway, bank transaction, three-way approval authority or production physical-lot accounting.
- Incoming invoice documents have evidence identifiers, but a supplied SHA-256 is not itself a byte-level PDF validation. Full attachment custody/approval remains to be integrated.
- Previous freeform PO lines and old stock history are not rewritten or assigned costs retroactively.
- Job costing is partial. Missing labor, overhead, scraps, unit conversions, material lot/warehouse identity and unassigned inventory are excluded. Never present its total as final COGS or job profitability.
- User-supplied local review names are not a verified identity; do not expose this beta to an untrusted shop network.
- Invoice edits, credit memos, returns and amended PO price revisions need separate reversal/version flows. This iteration holds conflicting source data rather than overwriting historical evidence.

## Verification

Python tests cover exact matching, missing price holds, partial receipt holds, cumulative overbilling, immutable invoice replays, source/unit mismatch, landed-cost arithmetic, reviewer-required variances, consumption quantity caps, job passport visibility, restart persistence and estimating feedback. Cross-repository regression and package builds must pass before merge.
