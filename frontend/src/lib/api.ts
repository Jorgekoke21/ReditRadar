import { getActiveToken, setActiveToken } from "./tokenStore";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8010";
const DEV_TOKEN_KEY = "radarin_radar_token";

/**
 * Token resolution order: an in-memory token set by AuthProvider from a live
 * Supabase session takes priority; otherwise fall back to the persisted dev
 * token (used by the dev-login flow, and directly by the E2E test suite,
 * which injects `dev:<uuid>` tokens via localStorage before navigating).
 */
export function getToken(): string | null {
  return getActiveToken() ?? localStorage.getItem(DEV_TOKEN_KEY);
}

export function setDevToken(token: string) {
  localStorage.setItem(DEV_TOKEN_KEY, token);
  setActiveToken(token);
}

export function clearToken() {
  localStorage.removeItem(DEV_TOKEN_KEY);
  setActiveToken(null);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    if (!window.location.pathname.startsWith("/login")) {
      window.location.href = "/login?reason=expired";
    }
    throw new ApiError(401, "Sesión expirada");
  }

  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body.detail || message;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  postForm: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
