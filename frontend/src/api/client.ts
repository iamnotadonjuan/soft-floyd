import { fetchEventSource } from "@microsoft/fetch-event-source";
import type {
  ActivitiesResponse,
  ActivityDetail,
  MessagesResponse,
  MonthlyCost,
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
