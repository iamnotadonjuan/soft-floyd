// Typed fetch wrapper. Components never call fetch() directly — see
// docs/FRONTEND.md.

import type {
  AccountOut,
  ActivityDetailOut,
  ActivitySummaryOut,
  BikeIn,
  BikeOut,
  CoachConversationDetailOut,
  CoachConversationOut,
  CoachEvent,
  CoachMemoryNoteOut,
  ConnectionOut,
  ExportFormat,
  LoginStartResult,
  ProfileIn,
  ProfileOut,
  SessionRequestIn,
  SessionStatus,
  TrainingSessionOut,
} from "./types";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`/api${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/me") {
      window.dispatchEvent(new Event("soft-floyd-unauthorized"));
    }
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
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, init);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// POSTs a coach message and calls onEvent for each Server-Sent Event as it
// arrives. EventSource can't POST, so this reads the body stream and splits
// SSE frames ("event: x\ndata: {...}\n\n") by hand. Resolves when the
// stream ends; rejects with ApiError if the turn is refused up front.
async function streamCoachMessage(
  conversationId: number,
  text: string,
  onEvent: (event: CoachEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await send(`/coach/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify({ text }),
    signal,
  });
  if (!response.body) throw new ApiError(500, "The coach reply had no body");
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = frame.split("\n").find((line) => line.startsWith("data: "));
      if (data) onEvent(JSON.parse(data.slice(6)) as CoachEvent);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

export const api = {
  getMe: () => request<AccountOut>("/auth/me"),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
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

  listCoachConversations: () => request<CoachConversationOut[]>("/coach/conversations"),
  createCoachConversation: () =>
    request<CoachConversationOut>("/coach/conversations", { method: "POST" }),
  getCoachConversation: (id: number) =>
    request<CoachConversationDetailOut>(`/coach/conversations/${id}`),
  deleteCoachConversation: (id: number) =>
    request<void>(`/coach/conversations/${id}`, { method: "DELETE" }),
  streamCoachMessage,
  listCoachMemory: () => request<CoachMemoryNoteOut[]>("/coach/memory"),
  deleteCoachMemory: (id: number) => request<void>(`/coach/memory/${id}`, { method: "DELETE" }),

  listTrainingSessions: () => request<TrainingSessionOut[]>("/training/sessions"),
  planTrainingSession: (data: SessionRequestIn) =>
    request<TrainingSessionOut>("/training/sessions", { method: "POST", body: JSON.stringify(data) }),
  getTrainingSession: (id: number) => request<TrainingSessionOut>(`/training/sessions/${id}`),
  regenerateTrainingSession: (id: number) =>
    request<TrainingSessionOut>(`/training/sessions/${id}/regenerate`, { method: "POST" }),
  updateTrainingSessionStatus: (id: number, status: SessionStatus) =>
    request<TrainingSessionOut>(`/training/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  deleteTrainingSession: (id: number) => request<void>(`/training/sessions/${id}`, { method: "DELETE" }),
  sendTrainingSessionToGarmin: (id: number) =>
    request<TrainingSessionOut>(`/training/sessions/${id}/garmin`, { method: "POST" }),
  // A direct download link — the browser follows it with the session
  // cookie, same-origin, and the server sets Content-Disposition; no
  // fetch() needed.
  trainingSessionExportUrl: (id: number, format: ExportFormat) =>
    `/api/training/sessions/${id}/export?format=${format}`,
};

export { ApiError };
