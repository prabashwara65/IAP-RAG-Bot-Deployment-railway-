/**
 * Typed client for the OIAP HR grounded answer endpoint.
 *
 * These interfaces mirror the backend wire contract exactly, including its
 * snake_case field names, so a contract change surfaces as a type error here
 * rather than as a silent runtime mismatch in a component.
 */

const DEFAULT_API_BASE_URL = "http://localhost:8000";
const ASK_PATH = "/api/v1/hr/ask";
const REQUEST_TIMEOUT_MS = 60_000;

/** Matches the backend `MAX_QUESTION_LENGTH`. */
export const MAX_QUESTION_LENGTH = 2000;
/** Matches the backend `MAX_TENANT_ID_LENGTH`. */
export const MAX_TENANT_ID_LENGTH = 120;

export interface HrCitation {
  citation_id: string;
  document_key: string;
  document_title: string;
  heading_path: string;
  chunk_index: number;
  distance: number;
}

export interface HrAskRequest {
  question: string;
  tenant_id: string;
}

export interface HrAskResponse {
  answer: string;
  citations: HrCitation[];
  insufficient_evidence: boolean;
}

/**
 * Why a request failed, in terms the UI can present safely.
 *
 * The backend deliberately returns curated messages, but this client never
 * displays them: it classifies the failure and lets the UI own the wording, so
 * no backend text can reach a user unreviewed.
 */
export type HrAskFailureKind =
  | "network"
  | "invalid_request"
  | "rate_limited"
  | "unavailable"
  | "upstream"
  | "unexpected";

export class HrAskError extends Error {
  readonly kind: HrAskFailureKind;
  readonly correlationId: string | null;

  constructor(kind: HrAskFailureKind, correlationId: string | null = null) {
    super(`HR ask request failed: ${kind}`);
    this.name = "HrAskError";
    this.kind = kind;
    this.correlationId = correlationId;
  }
}

function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL;
  return configured.replace(/\/+$/, "");
}

function failureKindForStatus(status: number): HrAskFailureKind {
  if (status === 422 || status === 400) {
    return "invalid_request";
  }
  if (status === 429) {
    return "rate_limited";
  }
  if (status === 503) {
    return "unavailable";
  }
  if (status === 502 || status === 504) {
    return "upstream";
  }
  return "unexpected";
}

function isHrCitation(value: unknown): value is HrCitation {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<HrCitation>;
  return (
    typeof candidate.citation_id === "string" &&
    typeof candidate.document_key === "string" &&
    typeof candidate.document_title === "string" &&
    typeof candidate.heading_path === "string" &&
    Number.isInteger(candidate.chunk_index) &&
    typeof candidate.distance === "number" &&
    Number.isFinite(candidate.distance)
  );
}

function isHrAskResponse(value: unknown): value is HrAskResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<HrAskResponse>;
  return (
    typeof candidate.answer === "string" &&
    typeof candidate.insufficient_evidence === "boolean" &&
    Array.isArray(candidate.citations) &&
    candidate.citations.every(isHrCitation)
  );
}

/**
 * Ask one grounded HR question.
 *
 * Throws {@link HrAskError} for every failure so callers handle one error type.
 */
export async function askHrQuestion(
  request: HrAskRequest,
  options: { signal?: AbortSignal } = {},
): Promise<HrAskResponse> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${ASK_PATH}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(request),
      signal: options.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch {
    throw new HrAskError("network");
  }

  const correlationId = response.headers.get("X-Correlation-ID");
  if (!response.ok) {
    throw new HrAskError(failureKindForStatus(response.status), correlationId);
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new HrAskError("unexpected", correlationId);
  }

  if (!isHrAskResponse(payload)) {
    throw new HrAskError("unexpected", correlationId);
  }
  return payload;
}
