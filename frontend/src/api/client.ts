import { fetchEventSource } from "@microsoft/fetch-event-source";
import type {
  ActivitiesResponse,
  ActivityDetail,
  DailySummaryResponse,
  MessagesResponse,
  MonthlyCost,
  Profile,
  SyncResult,
} from "./types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface ActivityFilter {
  bike_type?: string;
  page?: number;
  page_size?: number;
}

export function listActivities(filter: ActivityFilter = {}): Promise<ActivitiesResponse> {
  const params = new URLSearchParams();
  if (filter.bike_type) params.set("bike_type", filter.bike_type);
  if (filter.page !== undefined) params.set("page", String(filter.page));
  if (filter.page_size !== undefined) params.set("page_size", String(filter.page_size));
  const qs = params.toString();
  return get<ActivitiesResponse>(`/activities${qs ? "?" + qs : ""}`);
}

export function getActivity(id: number): Promise<ActivityDetail> {
  return get<ActivityDetail>(`/activities/${id}`);
}

export function getMessages(id: number): Promise<MessagesResponse> {
  return get<MessagesResponse>(`/activities/${id}/messages`);
}

export async function triggerAnalysis(id: number): Promise<string> {
  const res = await fetch(`${BASE}/activities/${id}/analysis`, { method: "POST" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  const data = (await res.json()) as { analysis: string };
  return data.analysis;
}

export function getMonthlyCost(): Promise<MonthlyCost> {
  return get<MonthlyCost>("/cost/month");
}

// Phase 4 — profile
export async function getProfile(): Promise<Profile | null> {
  const res = await fetch(`${BASE}/profile`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<Profile>;
}

export async function saveProfile(profile: Omit<Profile, "updated_at">): Promise<void> {
  const res = await fetch(`${BASE}/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
}

export async function syncGarmin(): Promise<SyncResult> {
  const res = await fetch(`${BASE}/sync/garmin`, { method: "POST" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<SyncResult>;
}

export async function getDailySummary(date?: string): Promise<DailySummaryResponse | null> {
  const url = `${BASE}/summary/daily${date ? `?date=${date}` : ""}`;
  const res = await fetch(url);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<DailySummaryResponse>;
}

export async function generateDailySummary(date?: string): Promise<DailySummaryResponse> {
  const url = `${BASE}/summary/daily${date ? `?date=${date}` : ""}`;
  const res = await fetch(url, { method: "POST" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<DailySummaryResponse>;
}

export function streamChat(
  id: number,
  message: string,
  onToken: (text: string) => void,
  onTool: (name: string) => void,
  onDone: () => void,
  onError: (err: string) => void,
): () => void {
  const ctrl = new AbortController();

  fetchEventSource(`${BASE}/activities/${id}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal: ctrl.signal,
    onmessage(ev) {
      if (ev.event === "token") onToken(ev.data);
      else if (ev.event === "tool") onTool(ev.data);
      else if (ev.event === "done") onDone();
      else if (ev.event === "error") onError(ev.data);
    },
    onerror(err) {
      onError(String(err));
      throw err; // stop retrying
    },
  }).catch(() => {
    // swallow — handled by onerror
  });

  return () => ctrl.abort();
}
