import { useEffect, useRef, useState } from "react";
import { askHrQuestion, HrAskError } from "../api/hrRag";
import type { HrAskFailureKind } from "../api/hrRag";
import { ChatComposer } from "./ChatComposer";
import { ChatMessage } from "./ChatMessage";
import type { ChatTurn } from "./ChatMessage";
import { ErrorNotice } from "./ErrorNotice";

const TENANT_ID = "tenant-synthetic";

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
        {turns.length === 0 && !isLoading ? (
          <p className="chat__empty">
            Ask a question to begin. Every answer is drawn only from approved HR
            documents, and its sources are listed underneath.
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
  );
}
