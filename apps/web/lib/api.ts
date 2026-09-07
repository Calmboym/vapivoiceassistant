/**
 * Thin fetch wrapper for the Charter123 API (Phase 4).
 *
 * Two things every authenticated call needs that a bare `fetch()` won't
 * give you for free:
 *   1. `credentials: "include"` — so the HttpOnly session cookie
 *      actually gets sent (and Set-Cookie responses get stored).
 *   2. The CSRF header on state-changing requests (§19) — the backend
 *      issues a *readable* `c123_csrf` cookie precisely so client JS can
 *      read it here and echo it back; see app/middleware/csrf.py.
 *
 * This file intentionally does NOT decide who's allowed to do what —
 * the backend is authoritative for every authorization decision (§35:
 * "Do not put authorization logic exclusively in React"). It only
 * carries identity (the cookie) and proves the request came from this
 * page (the CSRF header).
 */

export type ApiError = { code: string; message: string };
export type ApiEnvelope<T> =
  | { success: true; data: T; request_id: string }
  | { success: false; error: ApiError; request_id: string };

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiRequestError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");
  if (MUTATING_METHODS.has(method)) {
    const csrf = readCookie("c123_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  const response = await fetch(path, { ...init, method, headers, credentials: "include" });

  // 204/empty bodies (rare here, but don't choke on them).
  const text = await response.text();
  const body: ApiEnvelope<T> = text ? JSON.parse(text) : ({ success: true, data: undefined as T, request_id: "" } as ApiEnvelope<T>);

  if (!body.success) {
    throw new ApiRequestError(body.error.code, body.error.message, response.status);
  }
  return body.data;
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, json?: unknown) =>
    apiFetch<T>(path, { method: "POST", body: json !== undefined ? JSON.stringify(json) : undefined }),
};
