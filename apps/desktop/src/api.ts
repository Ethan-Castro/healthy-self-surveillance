import type {
  RescanResult,
  ReviewInput,
  SessionConfig,
  SessionSnapshot,
  SetupStatus,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const raw = await response.text();
    let detail = raw;

    try {
      const parsed = JSON.parse(raw) as { detail?: unknown };
      if (typeof parsed.detail === "string") {
        detail = parsed.detail;
      }
    } catch {
      // Keep the raw response text when the error payload is not JSON.
    }

    throw new Error(detail || `Request failed with ${response.status}`);
  }

  return (await response.json()) as T;
}

export function fetchSetup(): Promise<SetupStatus> {
  return api<SetupStatus>("/api/setup");
}

export function createSession(config: SessionConfig): Promise<SessionSnapshot> {
  return api<SessionSnapshot>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ config }),
  });
}

export function fetchSession(sessionId: string): Promise<SessionSnapshot> {
  return api<SessionSnapshot>(`/api/sessions/${sessionId}`);
}

export function transitionSession(
  sessionId: string,
  action: "start" | "pause" | "stop",
): Promise<SessionSnapshot> {
  return api<SessionSnapshot>(`/api/sessions/${sessionId}/${action}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function submitReview(
  sessionId: string,
  reviewInput: ReviewInput,
): Promise<SessionSnapshot> {
  return api<SessionSnapshot>(`/api/sessions/${sessionId}/review`, {
    method: "POST",
    body: JSON.stringify(reviewInput),
  });
}

export function saveSession(sessionId: string): Promise<SessionSnapshot> {
  return api<SessionSnapshot>(`/api/sessions/${sessionId}/save`, {
    method: "POST",
  });
}

export function rescanSession(sessionId: string): Promise<RescanResult> {
  return api<RescanResult>(`/api/sessions/${sessionId}/rescan`, {
    method: "POST",
  });
}
