// Typed fetch wrapper. Components never call fetch() directly — see
// docs/FRONTEND.md.

import type {
  ActivityDetailOut,
  ActivitySummaryOut,
  BikeIn,
  BikeOut,
  ConnectionOut,
  LoginStartResult,
  ProfileIn,
  ProfileOut,
} from "./types";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    // FastAPI's default error shape is {"detail": "..."} — surface that
    // message directly rather than the raw JSON envelope when possible.
    let message = body;
    try {
      const parsed = JSON.parse(body);
      if (typeof parsed?.detail === "string") message = parsed.detail;
    } catch {
      // body wasn't JSON — fall through and use it verbatim.
    }
    throw new ApiError(response.status, message || `${init?.method ?? "GET"} ${path} failed`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  getProfile: () => request<ProfileOut>("/profile"),
  updateProfile: (data: ProfileIn) =>
    request<ProfileOut>("/profile", { method: "PUT", body: JSON.stringify(data) }),
  listActivities: (cursor?: Pick<ActivitySummaryOut, "start_time" | "id">) => {
    const params = new URLSearchParams({ limit: "20" });
    if (cursor) {
      params.set("before_start_time", cursor.start_time);
      params.set("before_id", String(cursor.id));
    }
    return request<ActivitySummaryOut[]>(`/activities?${params}`);
  },
  getActivity: (id: number) => request<ActivityDetailOut>(`/activities/${id}`),

  listBikes: () => request<BikeOut[]>("/bikes"),
  addBike: (data: BikeIn) => request<BikeOut>("/bikes", { method: "POST", body: JSON.stringify(data) }),
  updateBike: (id: number, data: BikeIn) =>
    request<BikeOut>(`/bikes/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteBike: (id: number) => request<void>(`/bikes/${id}`, { method: "DELETE" }),

  listConnections: () => request<ConnectionOut[]>("/connections"),
  garminLogin: (email: string, password: string) =>
    request<LoginStartResult>("/connections/garmin/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  garminSubmitMfa: (code: string) =>
    request<LoginStartResult>("/connections/garmin/mfa", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  garminDisconnect: () => request<void>("/connections/garmin", { method: "DELETE" }),
};

export { ApiError };
