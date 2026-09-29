import { apiBaseUrl, authHeaders, jsonHeaders } from "./http";
import { setAccessToken } from "./session";

export type ThemePreference = "light" | "dark" | "system";

export interface Profile {
  id: string;
  email: string;
  display_name: string;
  theme: ThemePreference;
  has_avatar: boolean;
  two_factor_method?: string;
}

export interface OtpIssued {
  otp_sent: boolean;
  email: string;
  expires_in_seconds: number;
  otp_code: string | null;
  delivery: "email" | "on_screen";
}

export interface SessionPayload {
  access_token: string;
  token_type: string;
  user: Profile;
}

export type AuthFailureKind =
  | "network"
  | "invalid_request"
  | "conflict"
  | "not_found"
  | "unauthenticated"
  | "mail_failed"
  | "rate_limited"
  | "unexpected";

export class AuthApiError extends Error {
  readonly kind: AuthFailureKind;
  readonly code: string | null;

  constructor(
    kind: AuthFailureKind,
    message = AUTH_FAILURE_MESSAGES[kind],
    code: string | null = null,
  ) {
    super(message);
    this.name = "AuthApiError";
    this.kind = kind;
    this.code = code;
  }
}

function failureKind(status: number): AuthFailureKind {
  if (status === 401) {
    return "unauthenticated";
  }
  if (status === 404) {
    return "not_found";
  }
  if (status === 409) {
    return "conflict";
  }
  if (status === 422 || status === 400) {
    return "invalid_request";
  }
  if (status === 413) {
    return "invalid_request";
  }
  if (status === 429) {
    return "rate_limited";
  }
  if (status === 502) {
    return "mail_failed";
  }
  return "unexpected";
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    if (!response.ok) {
      return null;
    }
    throw new AuthApiError("unexpected");
  }
}

function serverErrorMessage(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null || !("error" in payload)) {
    return null;
  }
  const error = payload.error;
  if (typeof error !== "object" || error === null || !("message" in error)) {
    return null;
  }
  return typeof error.message === "string" && error.message.trim()
    ? error.message
    : null;
}

function serverErrorCode(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null || !("error" in payload)) {
    return null;
  }
  const error = payload.error;
  if (typeof error !== "object" || error === null || !("code" in error)) {
    return null;
  }
  return typeof error.code === "string" && error.code.trim()
    ? error.code
    : null;
}

function authError(response: Response, payload: unknown): AuthApiError {
  if (response.status >= 500) {
    return new AuthApiError("unexpected");
  }
  return new AuthApiError(
    failureKind(response.status),
    response.status >= 400 ? (serverErrorMessage(payload) ?? undefined) : undefined,
    response.status >= 400 ? serverErrorCode(payload) : null,
  );
}

function isProfile(value: unknown): value is Profile {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<Profile>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.email === "string" &&
    typeof candidate.display_name === "string" &&
    (candidate.theme === "light" ||
      candidate.theme === "dark" ||
      candidate.theme === "system") &&
    typeof candidate.has_avatar === "boolean"
  );
}

function isOtpIssued(value: unknown): value is OtpIssued {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<OtpIssued> & { delivery?: string };
  if (
    candidate.otp_sent !== true ||
    typeof candidate.email !== "string" ||
    typeof candidate.expires_in_seconds !== "number" ||
    !(candidate.otp_code === null || typeof candidate.otp_code === "string")
  ) {
    return false;
  }
  if (candidate.delivery === "email" || candidate.delivery === "on_screen") {
    return true;
  }
  candidate.delivery = candidate.otp_code === null ? "email" : "on_screen";
  return true;
}

function isSessionPayload(value: unknown): value is SessionPayload {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<SessionPayload>;
  return (
    typeof candidate.access_token === "string" &&
    typeof candidate.token_type === "string" &&
    isProfile(candidate.user)
  );
}

async function postAuth(path: string, body: unknown): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(body),
    });
  } catch {
    throw new AuthApiError("network");
  }
  const payload = await readJson(response);
  if (!response.ok) {
    throw authError(response, payload);
  }
  return payload;
}

export async function requestSignup(
  email: string,
  displayName: string,
  password: string,
): Promise<OtpIssued> {
  const payload = await postAuth("/api/v1/auth/signup", {
    email,
    display_name: displayName,
    password,
  });
  if (!isOtpIssued(payload)) {
    throw new AuthApiError("unexpected");
  }
  return payload;
}

export async function requestLogin(
  email: string,
  password: string,
): Promise<OtpIssued> {
  const payload = await postAuth("/api/v1/auth/login", { email, password });
  if (!isOtpIssued(payload)) {
    throw new AuthApiError("unexpected");
  }
  return payload;
}

export async function requestResetPassword(
  email: string,
  newPassword: string,
): Promise<OtpIssued> {
  const payload = await postAuth("/api/v1/auth/reset-password", {
    email,
    new_password: newPassword,
  });
  if (!isOtpIssued(payload)) {
    throw new AuthApiError("unexpected");
  }
  return payload;
}

export async function verifyOtp(email: string, code: string): Promise<SessionPayload> {
  const payload = await postAuth("/api/v1/auth/verify", { email, code });
  if (!isSessionPayload(payload)) {
    throw new AuthApiError("unexpected");
  }
  setAccessToken(payload.access_token);
  return payload;
}

export async function fetchProfile(): Promise<Profile> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/api/v1/me`, {
      headers: authHeaders(),
    });
  } catch {
    throw new AuthApiError("network");
  }
  const payload = await readJson(response);
  if (!response.ok) {
    throw authError(response, payload);
  }
  if (!isProfile(payload)) {
    throw new AuthApiError("unexpected");
  }
  return payload;
}

export async function updateProfile(patch: {
  display_name?: string;
  theme?: ThemePreference;
}): Promise<Profile> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/api/v1/me`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify(patch),
    });
  } catch {
    throw new AuthApiError("network");
  }
  const payload = await readJson(response);
  if (!response.ok) {
    throw authError(response, payload);
  }
  if (!isProfile(payload)) {
    throw new AuthApiError("unexpected");
  }
  return payload;
}

export async function uploadAvatar(file: File): Promise<Profile> {
  const headers = authHeaders();
  delete headers.Accept;
  let response: Response;
  try {
    const body = new FormData();
    body.append("file", file);
    response = await fetch(`${apiBaseUrl()}/api/v1/me/avatar`, {
      method: "POST",
      headers: { Authorization: headers.Authorization ?? "" },
      body,
    });
  } catch {
    throw new AuthApiError("network");
  }
  const payload = await readJson(response);
  if (!response.ok) {
    throw authError(response, payload);
  }
  if (!isProfile(payload)) {
    throw new AuthApiError("unexpected");
  }
  return payload;
}

export async function deleteAvatar(): Promise<Profile> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/api/v1/me/avatar`, {
      method: "DELETE",
      headers: authHeaders(),
    });
  } catch {
    throw new AuthApiError("network");
  }
  const payload = await readJson(response);
  if (!response.ok) {
    throw authError(response, payload);
  }
  if (!isProfile(payload)) {
    throw new AuthApiError("unexpected");
  }
  return payload;
}

export async function fetchAvatarBlob(): Promise<Blob | null> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/api/v1/me/avatar`, {
      headers: authHeaders(),
    });
  } catch {
    throw new AuthApiError("network");
  }
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    const payload = await readJson(response);
    throw authError(response, payload);
  }
  return response.blob();
}

export async function logout(): Promise<void> {
  try {
    await fetch(`${apiBaseUrl()}/api/v1/auth/logout`, {
      method: "POST",
      headers: authHeaders(),
    });
  } catch {
    // Clearing the local token still ends this browser session.
  } finally {
    setAccessToken(null);
  }
}

export const AUTH_FAILURE_MESSAGES: Record<AuthFailureKind, string> = {
  network: "Could not reach the assistant. Check that the backend is running.",
  invalid_request: "Check the details you entered and try again.",
  conflict: "An account with this email already exists. Log in instead.",
  not_found: "No account was found for that email. Sign up first.",
  unauthenticated: "That sign-in is no longer valid. Request a new code.",
  mail_failed: "The verification email could not be sent. Try again shortly.",
  rate_limited: "Too many attempts. Wait a minute and try again.",
  unexpected: "Something went wrong. Please try again.",
};