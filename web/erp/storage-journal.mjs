// Browser-local three-record recovery journal. This is not a SQL transaction.
export const JOURNAL_KEY = "axiom_erp_pending_save_v1";
const LIMITS = [1800000, 2500000, 800000];
function verify(record) {
  if (!record || record.version !== 1 || !Array.isArray(record.values) || record.values.length !== 3) throw Error("Invalid pending ERP save");
  record.values.forEach((value, i) => {
    if (typeof value !== "string" || value.length >= LIMITS[i]) throw Error("Oversized pending ERP save");
    JSON.parse(value);
  });
  return record.values;
}
export function recoverBrowserSave(storage, keys) {
  const pending = storage.getItem(JOURNAL_KEY);
  if (pending == null) return false;
  if (pending.length >= 5000000) throw Error("Oversized pending ERP journal");
  const values = verify(JSON.parse(pending));
  keys.forEach((key, i) => storage.setItem(key, values[i]));
  storage.removeItem(JOURNAL_KEY);
  return true;
}
export function persistBrowserSave(storage, keys, objects) {
  const values = objects.map(value => JSON.stringify(value));
  verify({version: 1, values});
  // A failed journal write leaves all three previous keys untouched.
  storage.setItem(JOURNAL_KEY, JSON.stringify({version: 1, values}));
  // Any failure below is recoverable on the next load.
  keys.forEach((key, i) => storage.setItem(key, values[i]));
  storage.removeItem(JOURNAL_KEY);
}
