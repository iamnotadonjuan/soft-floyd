const guideKey = (accountId: number) => `soft-floyd.first-use.${accountId}`;
const tourKey = (accountId: number) => `soft-floyd.app-tour.v1.${accountId}`;

export function isGuidePending(accountId: number): boolean {
  try { return localStorage.getItem(guideKey(accountId)) === "pending"; }
  catch { return false; }
}

export function setGuidePending(accountId: number, pending: boolean): void {
  try { localStorage.setItem(guideKey(accountId), pending ? "pending" : "dismissed"); }
  catch { /* The guide remains usable for this visit if storage is unavailable. */ }
}

export function hasSeenTour(accountId: number): boolean {
  try { return localStorage.getItem(tourKey(accountId)) === "seen"; }
  catch { return false; }
}

export function markTourSeen(accountId: number): void {
  try { localStorage.setItem(tourKey(accountId), "seen"); }
  catch { /* The tour can still be finished during this visit. */ }
}
