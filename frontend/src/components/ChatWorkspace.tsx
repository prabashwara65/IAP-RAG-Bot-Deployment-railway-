import { useEffect, useRef, useState } from "react";
import { askHrQuestion, HrAskError } from "../api/hrRag";
import type { HrAskFailureKind } from "../api/hrRag";
import { ChatComposer } from "./ChatComposer";
import { ChatMessage } from "./ChatMessage";
import type { ChatTurn } from "./ChatMessage";
import { ErrorNotice } from "./ErrorNotice";
import { DocumentUploadPanel } from "./DocumentUploadPanel";
import { DOCUMENT_TYPES } from "../api/documents";
import type { DocumentType } from "../api/documents";

const TENANT_ID = "real";

interface Failure {
  kind: HrAskFailureKind;
  correlationId: string | null;
}

interface ChatWorkspaceProps {
  onUnauthenticated: () => void;
}

export function ChatWorkspace({ onUnauthenticated }: ChatWorkspaceProps) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [documentType, setDocumentType] = useState<DocumentType | "">("");
  const endOfTranscript = useRef<HTMLDivElement>(null);
  const nextTurnId = useRef(0);

  useEffect(() => {
    endOfTranscript.current?.scrollIntoView({ block: "end" });
  }, [turns, isLoading, failure]);

  function createTurnId(): string {
    nextTurnId.current += 1;
    return `turn-${nextTurnId.current}`;
  }

  async function handleAsk(question: string) {
    if (isLoading) {
      return;
    }

    setFailure(null);
    setTurns((previous) => [
      ...previous,
      { id: createTurnId(), role: "user", question },
    ]);
    setIsLoading(true);

    try {
      const response = await askHrQuestion({
        question,
        tenant_id: TENANT_ID,
        ...(documentType === "" ? {} : { document_type: documentType }),
      });
      setTurns((previous) => [
        ...previous,
        { id: createTurnId(), role: "assistant", response },
      ]);
    } catch (error) {
      const kind =
        error instanceof HrAskError ? error.kind : "unexpected";

      if (kind === "unauthenticated") {
        onUnauthenticated();
      }

      setFailure(
        error instanceof HrAskError
          ? { kind: error.kind, correlationId: error.correlationId }
          : { kind: "unexpected", correlationId: null },
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="chat">
      <div className="chat__transcript" role="log" aria-label="Conversation">
        {turns.length === 0 ? (
          <section className="chat-welcome" aria-label="Get started">
            <h2 className="chat-welcome__title">
              Welcome to the HR assistant
            </h2>
            <p className="chat-welcome__description">
              Ask a question about your workplace policies using the box below.
            </p>
          </section>
        ) : null}

        {turns.map((turn) => (
          <ChatMessage key={turn.id} turn={turn} />
        ))}

        {isLoading ? (
          <p className="message message--pending" role="status">
            Searching approved HR sources&hellip;
          </p>
        ) : null}

        {failure === null ? null : (
          <ErrorNotice
            correlationId={failure.correlationId}
            kind={failure.kind}
          />
        )}

        <div ref={endOfTranscript} />
      </div>

      <DocumentUploadPanel onUnauthenticated={onUnauthenticated} />
      <label className="chat__type-filter">
        Search document type
        <select
          aria-label="Search document type"
          disabled={isLoading}
          onChange={(event) => setDocumentType(event.target.value as DocumentType | "")}
          value={documentType}
        >
          <option value="">All types</option>
          {DOCUMENT_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
        </select>
      </label>
      <ChatComposer
        isLoading={isLoading}
        onAsk={(question) => {
          void handleAsk(question);
        }}
      />
    </main>
  );
}