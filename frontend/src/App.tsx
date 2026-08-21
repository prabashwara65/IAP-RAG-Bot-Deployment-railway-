import { useEffect, useRef, useState } from "react";
import { askHrQuestion, HrAskError } from "./api/hrRag";
import type { HrAskFailureKind } from "./api/hrRag";
import { ChatComposer } from "./components/ChatComposer";
import { ChatMessage } from "./components/ChatMessage";
import type { ChatTurn } from "./components/ChatMessage";
import { ErrorNotice } from "./components/ErrorNotice";

/**
 * Fixed internal routing value for this public demo. It selects which tenant's
 * approved HR documents are searched. It is not sign-in, grants no access
 * rights, and is deliberately not editable by the reader.
 */
const TENANT_ID = "tenant-synthetic";

interface Failure {
  kind: HrAskFailureKind;
  correlationId: string | null;
}

/**
 * Conversational HR assistant.
 *
 * Every turn is kept in state for the browser session, so the transcript grows
 * rather than being replaced. Each question is still an independent call to
 * `POST /api/v1/hr/ask`: no prior turns are sent, because the backend has no
 * conversation memory and grounds each answer only in retrieved HR sources.
 */
export function App() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
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
      });
      setTurns((previous) => [
        ...previous,
        { id: createTurnId(), role: "assistant", response },
      ]);
    } catch (error) {
      // The failed turn keeps the reader's question visible, so the transcript
      // still shows what was asked when the answer could not be produced.
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
    <div className="page">
      <header className="page__header">
        <h1 className="page__title">OIAP HR Assistant</h1>
        <p className="page__subtitle">
          Ask questions using approved HR knowledge.
        </p>
      </header>

      <main className="chat">
        <div className="chat__transcript" role="log" aria-label="Conversation">
          {turns.length === 0 && !isLoading ? (
            <p className="chat__empty">
              Ask a question to begin. Every answer is drawn only from approved
              HR documents, and its sources are listed underneath.
            </p>
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

        <ChatComposer
          isLoading={isLoading}
          onAsk={(question) => {
            void handleAsk(question);
          }}
        />
      </main>

      <footer className="page__footer">
        <p>
          Answers are generated only from HR documents approved for retrieval.
          Always confirm anything consequential with your HR team.
        </p>
      </footer>
    </div>
  );
}
