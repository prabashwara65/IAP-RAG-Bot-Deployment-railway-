import { apiBaseUrl, authHeaders, jsonHeaders } from "./http";

export interface CalendarEvent {
  id: string;
  title: string;
  description: string | null;
  event_date: string;
  event_time: string | null;
  completed: boolean;
  cancelled: boolean;
  confirmation_email_sent: boolean;
  created_at: string;
  updated_at: string;
}
export interface EventInput {
  send_email: boolean;
  title: string;
  description?: string | null;
  event_date: string;
  event_time?: string | null;
}
export interface CreatedEvent extends CalendarEvent { email_sent: boolean }
export interface ConfirmedEvent extends CalendarEvent { email_sent: boolean }
export class EventApiError extends Error {
  readonly kind: "unauthenticated" | "invalid" | "unavailable" | "network";
  constructor(kind: EventApiError["kind"]) {
    super("The events request could not be completed.");
    this.name = "EventApiError";
    this.kind = kind;
  }
}
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
export function isCalendarDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const instant = new Date(value + "T12:00:00Z");
  return Number.isFinite(instant.getTime()) && instant.toISOString().slice(0, 10) === value;
}
function isEvent(value: unknown): value is CalendarEvent {
  return object(value)
    && typeof value.id === "string" && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value.id)
    && typeof value.title === "string" && value.title.trim().length > 0 && value.title.length <= 200
    && (value.description === null || (typeof value.description === "string" && value.description.length <= 2000))
    && isCalendarDate(value.event_date)
    && (value.event_time === null || (typeof value.event_time === "string" && /^([01]\d|2[0-3]):[0-5]\d(:00)?$/.test(value.event_time)))
    && typeof value.completed === "boolean" && typeof value.cancelled === "boolean" && typeof value.confirmation_email_sent === "boolean"
    && (!value.confirmation_email_sent || value.completed)
    && typeof value.created_at === "string" && Number.isFinite(Date.parse(value.created_at))
    && typeof value.updated_at === "string" && Number.isFinite(Date.parse(value.updated_at));
}
async function request(path: string, init: RequestInit, expectedStatus?: number): Promise<unknown> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 35_000);
  try {
    const response = await fetch(apiBaseUrl() + "/api/v1/events" + path, { ...init, signal: controller.signal });
    if (!response.ok) {
      throw new EventApiError(response.status === 401 ? "unauthenticated" : response.status === 422 ? "invalid" : "unavailable");
    }
    if (expectedStatus !== undefined && response.status !== expectedStatus) throw new EventApiError("unavailable");
    if (response.status === 204) return undefined;
    try { return await response.json() as unknown; }
    catch { throw new EventApiError("unavailable"); }
  } catch (error) {
    if (error instanceof EventApiError) throw error;
    throw new EventApiError("network");
  } finally { window.clearTimeout(timer); }
}
export async function fetchCalendarTimezone(): Promise<string> {
  const result = await request("/settings", { headers: authHeaders() });
  if (!object(result) || typeof result.timezone !== "string") throw new EventApiError("unavailable");
  try { new Intl.DateTimeFormat("en-GB", { timeZone: result.timezone }).format(); }
  catch { throw new EventApiError("unavailable"); }
  return result.timezone;
}
export async function fetchEvents(): Promise<CalendarEvent[]> {
  const result = await request("", { headers: authHeaders() });
  if (!Array.isArray(result) || !result.every(isEvent)) throw new EventApiError("unavailable");
  return result;
}
export async function createEvent(input: EventInput): Promise<CreatedEvent> {
  const result = await request("", { method: "POST", headers: jsonHeaders(), body: JSON.stringify(input) });
  if (!isEvent(result) || result.completed || result.cancelled || result.confirmation_email_sent
    || !("email_sent" in result) || typeof result.email_sent !== "boolean"
    || (!input.send_email && result.email_sent)) throw new EventApiError("unavailable");
  return result as CreatedEvent;
}
export async function confirmEvent(id: string): Promise<ConfirmedEvent> {
  const result = await request("/" + encodeURIComponent(id) + "/confirm", { method: "PATCH", headers: authHeaders() });
  if (!isEvent(result) || result.id !== id || !result.completed || result.cancelled || !("email_sent" in result) || typeof result.email_sent !== "boolean") {
    throw new EventApiError("unavailable");
  }
  return result as ConfirmedEvent;
}
export async function cancelEvent(id: string): Promise<CalendarEvent> {
  const result = await request("/" + encodeURIComponent(id) + "/cancel", { method: "PATCH", headers: authHeaders() });
  if (!isEvent(result) || result.id !== id || !result.cancelled) throw new EventApiError("unavailable");
  return result;
}
export async function deleteEvent(id: string): Promise<void> {
  await request("/" + encodeURIComponent(id), { method: "DELETE", headers: authHeaders() }, 204);
}
export function calendarToday(timezone: string, now = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(now);
  const part = (type: string) => parts.find((entry) => entry.type === type)?.value ?? "";
  return part("year") + "-" + part("month") + "-" + part("day");
}
