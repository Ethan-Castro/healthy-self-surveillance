import type {
  RescanResult,
  ReviewInput,
  SessionConfig,
  SessionReviewDetail,
  SessionSnapshot,
  SetupStatus,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

function normalizeHeaders(headers?: HeadersInit): Record<string, string> {
  if (!headers) {
    return {};
  }
  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries());
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers);
  }
  return headers;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = {
    ...(init?.body ? { "Content-Type": "application/json" } : {}),
    ...normalizeHeaders(init?.headers),
  };
  let ok: boolean;
  let status: number;
  let raw: string;
  try {
    if (window.desktopShell?.apiRequest) {
      const response = await window.desktopShell.apiRequest({
        url: `${API_BASE}${path}`,
        method: init?.method,
        headers,
        body: typeof init?.body === "string" ? init.body : undefined,
      });
      ok = response.ok;
      status = response.status;
      raw = response.text;
    } else {
      const response = await fetch(`${API_BASE}${path}`, {
        headers,
        ...init,
      });
      ok = response.ok;
      status = response.status;
      raw = await response.text();
    }
  } catch (caught) {
    const message = caught instanceof Error ? caught.message : "Failed to fetch";
    throw new Error(
      `Cannot reach the local Focus Buddy service at ${API_BASE}. ${message}`,
    );
  }

  if (!ok) {
    let detail = raw;

    try {
      const parsed = JSON.parse(raw) as { detail?: unknown };
      if (typeof parsed.detail === "string") {
        detail = parsed.detail;
      }
    } catch {
      // Keep the raw response text when the error payload is not JSON.
    }

    throw new Error(detail || `Request failed with ${status}`);
  }

  return JSON.parse(raw) as T;
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

export function fetchSessions(): Promise<SessionSnapshot[]> {
  return api<SessionSnapshot[]>("/api/sessions");
}

export function fetchSession(sessionId: string): Promise<SessionSnapshot> {
  return api<SessionSnapshot>(`/api/sessions/${sessionId}`);
}

export function fetchSessionReview(sessionId: string): Promise<SessionReviewDetail> {
  return api<SessionReviewDetail>(`/api/sessions/${sessionId}/review`);
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
