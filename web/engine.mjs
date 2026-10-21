/* Axiom browser lab math and replayable hash ledger.
 * Educational, synthetic data. This module has no live ERP connection.
 */
export function quoteTotal({ quantity, materialEach, hoursEach, shopRate, outsideEach = 0, setup = 0, scrapPct = 0, marginPct = 0 }) {
  const p = { quantity, materialEach, hoursEach, shopRate, outsideEach, setup, scrapPct, marginPct };
  for (const [name, value] of Object.entries(p)) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) throw Error(name + " must be nonnegative and finite");
  }
  if (!Number.isSafeInteger(quantity) || quantity < 1) throw Error("quantity must be a positive integer");
  if (scrapPct > 100 || marginPct >= 100) throw Error("scrap or margin outside allowed range");
  const cost = ((materialEach * (1 + scrapPct / 100)) + hoursEach * shopRate + outsideEach) * quantity + setup;
  const total = cost / (1 - marginPct / 100);
  if (!Number.isFinite(total) || total > Number.MAX_SAFE_INTEGER / 100) throw Error("quote overflow");
  // Browser lab arithmetic: production Python quote validation uses Decimal.
  return Math.round((total + Number.EPSILON) * 100) / 100;
}

export function measurementResult(char, raw) {
  if (raw === "" || raw === null || raw === undefined) return "PENDING";
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n)) return "INVALID";
  if (char.lsl != null && n < char.lsl) return "FAIL";
  if (char.usl != null && n > char.usl) return "FAIL";
  return "PASS";
}

export function inspectionSummary(chars, values) {
  const results = chars.map(ch => measurementResult(ch, values[ch.id] ?? ""));
  return {
    pass: results.filter(x => x === "PASS").length,
    fail: results.filter(x => x === "FAIL").length,
    pending: results.filter(x => x === "PENDING").length,
    invalid: results.filter(x => x === "INVALID").length,
    // An inspection complete is not a released or approved FAI.
    status: results.some(x => x === "FAIL" || x === "INVALID") ? "BLOCKED" :
      results.some(x => x === "PENDING") ? "REVIEW REQUIRED" : "MEASURED / AWAITING APPROVAL"
  };
}

export function stable(value) {
  if (Array.isArray(value)) return "[" + value.map(stable).join(",") + "]";
  if (value && typeof value === "object") {
    return "{" + Object.keys(value).sort().map(k => JSON.stringify(k) + ":" + stable(value[k])).join(",") + "}";
  }
  return JSON.stringify(value);
}

export async function sha256(text) {
  const data = new TextEncoder().encode(text);
  const bytes = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(bytes)].map(b => b.toString(16).padStart(2, "0")).join("");
}

export async function appendEvent(ledger, { type, payload }) {
  const seq = ledger.length + 1;
  const previous = ledger.length ? ledger[ledger.length - 1].digest : "GENESIS";
  const event = { seq, previous, type, payload };
  const digest = await sha256(stable(event));
  return [...ledger, { ...event, digest }];
}

export async function verifyLedger(ledger) {
  let previous = "GENESIS";
  for (const [index, item] of ledger.entries()) {
    if (item.seq !== index + 1 || item.previous !== previous) return false;
    const { digest, ...event } = item;
    if (await sha256(stable(event)) !== digest) return false;
    previous = digest;
  }
  return true;
}
