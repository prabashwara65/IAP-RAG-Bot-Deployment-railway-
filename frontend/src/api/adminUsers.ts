import type { Profile, UserRole } from "./auth";
import { isProfile } from "./auth";
import { apiBaseUrl, authHeaders, jsonHeaders } from "./http";

export type AssignedRole = Exclude<UserRole, "user">;

export const ROLE_OPTIONS: ReadonlyArray<{
  value: AssignedRole;
  label: string;
}> = [
  { value: "admin", label: "Admin" },
  { value: "hr", label: "HR" },
  { value: "employee", label: "Employee" },
  { value: "student", label: "Student" },
];

export const ROLE_LABELS: Record<UserRole, string> = {
  user: "User",
  admin: "Admin",
  hr: "HR",
  employee: "Employee",
  student: "Student",
};

export interface UserList {
  users: Profile[];
  total: number;
  page: number;
  page_size: number;
}

export class AdminUsersError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "AdminUsersError";
    this.status = status;
  }
}

async function request(path: string, init: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new AdminUsersError(0, "Could not reach the assistant. Please try again.");
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    let message = response.status === 403
      ? "Only administrators can manage users."
      : response.status === 401
        ? "Your session has expired. Please sign in again."
        : "Could not complete this request. Please try again.";
    if (response.status < 500 && typeof body === "object" && body !== null) {
      const payload = body as { error?: { message?: unknown }; detail?: unknown };
      const supplied = payload.error?.message ?? payload.detail;
      if (typeof supplied === "string") message = supplied;
    }
    throw new AdminUsersError(response.status, message);
  }
  return body;
}

export async function fetchUsers(
  search: string, page: number, signal: AbortSignal,
): Promise<UserList> {
  const params = new URLSearchParams({ search, page: String(page), page_size: "20" });
  const payload = await request(`/api/v1/admin/users?${params}`, {
    headers: authHeaders(), signal,
  });
  const candidate = payload as Partial<UserList> | null;
  if (
    !candidate || !Array.isArray(candidate.users) ||
    !candidate.users.every(isProfile) ||
    typeof candidate.total !== "number" ||
    typeof candidate.page !== "number" ||
    typeof candidate.page_size !== "number"
  ) {
    throw new AdminUsersError(0, "The user list could not be loaded.");
  }
  return candidate as UserList;
}

export async function assignRole(userId: string, role: AssignedRole): Promise<Profile> {
  const payload = await request(`/api/v1/admin/users/${encodeURIComponent(userId)}/role`, {
    method: "PATCH", headers: jsonHeaders(), body: JSON.stringify({ role }),
  });
  if (typeof payload !== "object" || payload === null || !("user" in payload) ||
      !isProfile(payload.user)) {
    throw new AdminUsersError(0, "The role update could not be confirmed.");
  }
  return payload.user;
}