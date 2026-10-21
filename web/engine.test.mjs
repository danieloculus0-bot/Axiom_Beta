import test from "node:test";
import assert from "node:assert/strict";
import { quoteTotal, measurementResult, inspectionSummary, appendEvent, verifyLedger } from "./engine.mjs";

test("quote recalculates and rejects invalid quantities and margins", () => {
  const input = { quantity: 10, materialEach: 20, hoursEach: 1, shopRate: 50, outsideEach: 0, setup: 100, scrapPct: 10, marginPct: 20 };
  assert.equal(quoteTotal(input), 1025);
  assert.throws(() => quoteTotal({ ...input, marginPct: 100 }), /scrap or margin/);
  assert.throws(() => quoteTotal({ ...input, quantity: 1.5 }), /quantity/);
  assert.throws(() => quoteTotal({ ...input, materialEach: Infinity }), /materialEach/);
});
test("FAI remains pending until all measurements exist; no automatic approval", () => {
  const chars = [{ id: "a", lsl: 9.9, usl: 10.1 }, { id: "b", lsl: 4.95, usl: 5.05 }];
  assert.equal(measurementResult(chars[0], "10.1"), "PASS");
  assert.equal(measurementResult(chars[0], "10.2"), "FAIL");
  assert.equal(measurementResult(chars[0], "oops"), "INVALID");
  assert.equal(inspectionSummary(chars, {}).status, "REVIEW REQUIRED");
  assert.equal(inspectionSummary(chars, { a: 10, b: 5 }).status, "MEASURED / AWAITING APPROVAL");
  assert.equal(inspectionSummary(chars, { a: 10.2, b: 5 }).status, "BLOCKED");
});
test("hash ledger detects changes and wrong chain", async () => {
  let ledger = [];
  ledger = await appendEvent(ledger, { type: "scenario.opened", payload: { job: "WO-1001" } });
  ledger = await appendEvent(ledger, { type: "quote.recalculated", payload: { total: 1025 } });
  assert.equal(await verifyLedger(ledger), true);
  assert.equal(await verifyLedger([{ ...ledger[0], payload: { job: "WO-TAMPER" } }, ledger[1]]), false);
  assert.equal(await verifyLedger([{ ...ledger[0], previous: "different" }, ledger[1]]), false);
  assert.equal(await verifyLedger([ledger[1]]), false);
});
