// Typed fetch wrapper. Components never call fetch() directly — see
// docs/FRONTEND.md.

import type { ProfileIn, ProfileOut } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${response.status} ${body}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  getProfile: () => request<ProfileOut>("/profile"),
  updateProfile: (data: ProfileIn) =>
    request<ProfileOut>("/profile", { method: "PUT", body: JSON.stringify(data) }),
  listActivities: () => request<unknown[]>("/activities"),
};
