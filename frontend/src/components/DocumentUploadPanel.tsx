import { useRef, useState } from "react";
import { DOCUMENT_TYPES, DocumentUploadError, uploadDocument } from "../api/documents";
import type { DocumentIngestionResult, DocumentType, DocumentUploadFailureKind } from "../api/documents";

interface DocumentUploadPanelProps {
  onUnauthenticated: () => void;
}

const ERROR_MESSAGES: Record<DocumentUploadFailureKind, string> = {
  network: "Could not reach the document service. Try again.",
  unsupported: "Choose a TXT, Markdown, PDF, or DOCX file.",
  invalid: "This file could not be read, or it contains no extractable text.",
  too_large: "The file is larger than the 20 MB upload limit.",
  unauthenticated: "Your session has ended. Sign in again to upload documents.",
  unexpected: "The document could not be processed. Try another file.",
};

export function DocumentUploadPanel({ onUnauthenticated }: DocumentUploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<DocumentIngestionResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [documentType, setDocumentType] = useState<DocumentType>("Other");

  async function handleFile(file: File | undefined) {
    if (file === undefined) return;

    setIsUploading(true);
    setResult(null);
    setErrorMessage(null);
    try {
      setResult(await uploadDocument(file, documentType));
    } catch (error) {
      const kind = error instanceof DocumentUploadError ? error.kind : "unexpected";
      if (kind === "unauthenticated") onUnauthenticated();
      setErrorMessage(ERROR_MESSAGES[kind]);
    } finally {
      setIsUploading(false);
      if (inputRef.current !== null) inputRef.current.value = "";
    }
  }

  return (
    <section className="document-upload" aria-labelledby="document-upload-title">
      <div className="document-upload__heading">
        <div>
          <h2 id="document-upload-title">Read and chunk a document</h2>
          <p>TXT, Markdown, PDF, or DOCX · up to 20 MB</p>
        </div>
        <label className="document-upload__type-label">
          Document type
          <select
            aria-label="Document type for upload"
            disabled={isUploading}
            onChange={(event) => setDocumentType(event.target.value as DocumentType)}
            value={documentType}
          >
            {DOCUMENT_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
          </select>
        </label>
        <label className="document-upload__button">
          <input
            accept=".txt,.md,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            disabled={isUploading}
            onChange={(event) => void handleFile(event.currentTarget.files?.[0])}
            ref={inputRef}
            type="file"
          />
          {isUploading ? "Reading…" : "Choose document"}
        </label>
      </div>

      {errorMessage !== null ? <p className="document-upload__error" role="alert">{errorMessage}</p> : null}

      {result !== null ? (
        <div className="document-upload__result" aria-live="polite">
          <p className="document-upload__summary">
            {result.filename} <span>{result.chunk_count} {result.chunk_count === 1 ? "chunk" : "chunks"}</span>
          </p>
          <p className="document-upload__status" role="status">
            Stored as {result.document_type}, as a candidate. It is not searchable until approved.
          </p>
          <p className="document-upload__key">Document key: {result.document_key}</p>
          <ol className="document-upload__chunks">
            {result.chunks.map((chunk) => (
              <li key={`${chunk.chunk_index}-${chunk.content_hash}`}>
                <span>Chunk {chunk.chunk_index + 1}</span>
                <p>{chunk.content_text}</p>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  );
}