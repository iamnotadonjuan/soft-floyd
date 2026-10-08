const guideKey = (accountId: number) => `soft-floyd.first-use.${accountId}`;

export function isGuidePending(accountId: number): boolean {
  try { return localStorage.getItem(guideKey(accountId)) === "pending"; }
  catch { return false; }
}

export function setGuidePending(accountId: number, pending: boolean): void {
  try { localStorage.setItem(guideKey(accountId), pending ? "pending" : "dismissed"); }
  catch { /* The guide remains usable for this visit if storage is unavailable. */ }
}
