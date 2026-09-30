import { apiBaseUrl, authHeaders } from "./http";

const INGEST_PATH = "/api/v1/documents/ingest";
export const DOCUMENT_TYPES = [
  "Policy",
  "Procedure",
  "Company Profile",
  "Organization Structure",
  "Department Directory",
  "Employee Responsibility Directory",
  "Responsibility Matrix",
  "Approval Matrix",
  "Escalation Matrix",
  "FAQ",
  "Technical Guideline",
  "Contact Directory",
  "Project Proposal",
  "Proposal",
  "CV",
  "Resume",
  "Report",
  "Meeting Notes",
  "Requirements",
  "Contract",
  "Invoice",
  "Other",
] as const;
export type DocumentType = (typeof DOCUMENT_TYPES)[number];

export interface DocumentChunk {
  chunk_index: number;
  content_text: string;
  content_hash: string;
}

export interface DocumentIngestionResult {
  filename: string;
  document_type: DocumentType;
  document_key: string;
  version_id: string;
  version_status: string;
  chunk_count: number;
  chunks: DocumentChunk[];
}

export type DocumentUploadFailureKind =
  | "network"
  | "unsupported"
  | "invalid"
  | "too_large"
  | "unauthenticated"
  | "unexpected";

export class DocumentUploadError extends Error {
  readonly kind: DocumentUploadFailureKind;

  constructor(kind: DocumentUploadFailureKind) {
    super(`Document upload failed: ${kind}`);
    this.name = "DocumentUploadError";
    this.kind = kind;
  }
}

function isDocumentIngestionResult(value: unknown): value is DocumentIngestionResult {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<DocumentIngestionResult>;
  return (
    typeof candidate.filename === "string" &&
    typeof candidate.document_type === "string" &&
    DOCUMENT_TYPES.includes(candidate.document_type as DocumentType) &&
    typeof candidate.document_key === "string" &&
    typeof candidate.version_id === "string" &&
    typeof candidate.version_status === "string" &&
    Number.isInteger(candidate.chunk_count) &&
    Array.isArray(candidate.chunks) &&
    candidate.chunks.every((chunk) =>
      typeof chunk === "object" &&
      chunk !== null &&
      Number.isInteger((chunk as DocumentChunk).chunk_index) &&
      typeof (chunk as DocumentChunk).content_text === "string" &&
      typeof (chunk as DocumentChunk).content_hash === "string"
    )
  );
}

function failureKindForStatus(status: number): DocumentUploadFailureKind {
  if (status === 413) return "too_large";
  if (status === 415) return "unsupported";
  if (status === 401) return "unauthenticated";
  if (status === 422) return "invalid";
  return "unexpected";
}

export async function uploadDocument(
  file: File,
  documentType: DocumentType,
): Promise<DocumentIngestionResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("document_type", documentType);

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${INGEST_PATH}`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
      signal: AbortSignal.timeout(60_000),
    });
  } catch {
    throw new DocumentUploadError("network");
  }

  if (!response.ok) {
    throw new DocumentUploadError(failureKindForStatus(response.status));
  }

  try {
    const payload: unknown = await response.json();
    if (isDocumentIngestionResult(payload)) {
      return payload;
    }
  } catch {
    throw new DocumentUploadError("unexpected");
  }
  throw new DocumentUploadError("unexpected");
}