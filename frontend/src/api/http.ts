import { getAccessToken } from "./session";



export function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL ?? "";
  return configured.replace(/\/+$/, "");
}

export function jsonHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  const token = getAccessToken();
  if (token !== null) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getAccessToken();
  if (token !== null) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}
