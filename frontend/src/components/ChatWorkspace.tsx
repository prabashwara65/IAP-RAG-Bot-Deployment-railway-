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
import type { UserRole } from "../api/auth";
import { getSavedChat, saveChatSession } from "../api/savedChats";
import { RecentChatsDrawer } from "./RecentChatsDrawer";
import {
  clearActiveChat,
  loadActiveChat,
  saveActiveChat,
} from "../services/activeChatStorage";

const TENANT_ID = "tenant-real";

interface Failure {
  kind: HrAskFailureKind;
  correlationId: string | null;
}

interface ChatWorkspaceProps {
  userRole: UserRole | undefined;
  onUnauthenticated: () => void;
  userId?: string | undefined;
}

export function ChatWorkspace({
  onUnauthenticated,
  userId = "default",
  userRole,
}: ChatWorkspaceProps) {
  const [turns, setTurns] = useState<ChatTurn[]>(() => loadActiveChat(userId));
  const [isLoading, setIsLoading] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [documentType, setDocumentType] = useState<DocumentType | "">("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveToast, setSaveToast] = useState<string | null>(null);

  const endOfTranscript = useRef<HTMLDivElement>(null);
  const nextTurnId = useRef(turns.length);

  // Sync active ongoing turns with browser local storage on every update
  useEffect(() => {
    saveActiveChat(userId, turns);
  }, [turns, userId]);

  useEffect(() => {
    endOfTranscript.current?.scrollIntoView({ block: "end" });
  }, [turns, isLoading, failure]);

  function createTurnId(): string {
    nextTurnId.current += 1;
    return `turn-${Date.now()}-${nextTurnId.current}`;
  }

  function handleNewChat() {
    setTurns([]);
    setFailure(null);
    clearActiveChat(userId);
    setSaveToast(null);
  }

  async function handleSaveChat() {
    if (turns.length === 0 || isSaving) return;

    setIsSaving(true);
    setSaveToast(null);

    try {
      await saveChatSession(turns);
      setSaveToast("Chat saved to account!");
      window.setTimeout(() => setSaveToast(null), 3500);
    } catch {
      setSaveToast("Failed to save chat.");
      window.setTimeout(() => setSaveToast(null), 3500);
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSelectSavedChat(chatId: string) {
    try {
      setIsLoading(true);
      setFailure(null);

      const detail = await getSavedChat(chatId);

      setTurns(detail.messages);
      saveActiveChat(userId, detail.messages);
    } catch (error) {
      const kind =
        error instanceof HrAskError ? error.kind : "unexpected";

      if (kind === "unauthenticated") {
        onUnauthenticated();
      }

      setFailure({
        kind: "unexpected",
        correlationId: null,
      });
    } finally {
      setIsLoading(false);
    }
  }

  async function handleAsk(question: string) {
    if (isLoading) {
      return;
    }

    setFailure(null);

    setTurns((previous) => [
      ...previous,
      {
        id: createTurnId(),
        role: "user",
        question,
      },
    ]);

    setIsLoading(true);

    try {
      const response = await askHrQuestion({
        question,
        tenant_id: TENANT_ID,
        ...(userRole === "admin" && documentType !== ""
          ? { document_type: documentType }
          : {}),
      });

      setTurns((previous) => [
        ...previous,
        {
          id: createTurnId(),
          role: "assistant",
          response,
        },
      ]);
    } catch (error) {
      const kind =
        error instanceof HrAskError ? error.kind : "unexpected";

      if (kind === "unauthenticated") {
        onUnauthenticated();
      }

      setFailure(
        error instanceof HrAskError
          ? {
              kind: error.kind,
              correlationId: error.correlationId,
            }
          : {
              kind: "unexpected",
              correlationId: null,
            },
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="chat">
      <div className="chat__toolbar">
        <div className="chat__toolbar-actions">
          <button
            type="button"
            className="chat__toolbar-btn"
            onClick={handleNewChat}
            title="Clear active chat and start fresh"
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>New Chat</span>
          </button>

          <button
            type="button"
            className="chat__toolbar-btn chat__toolbar-btn--save"
            onClick={() => void handleSaveChat()}
            disabled={turns.length === 0 || isSaving}
            title={
              turns.length === 0
                ? "Ask a question to save conversation"
                : "Save this chat to your account"
            }
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
              <polyline points="17 21 17 13 7 13 7 21" />
              <polyline points="7 3 7 8 15 8" />
            </svg>
            <span>{isSaving ? "Saving…" : "Save Chat"}</span>
          </button>

          <button
            type="button"
            className="chat__toolbar-btn"
            onClick={() => setDrawerOpen(true)}
            title="Open recent saved chats"
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            <span>Recent Chats</span>
          </button>

          {saveToast ? (
            <span className="chat__toolbar-toast" role="status">
              ✓ {saveToast}
            </span>
          ) : null}
        </div>
      </div>

      <div
        className="chat__transcript"
        role="log"
        aria-label="Conversation"
      >
        {turns.length === 0 ? (
          <section className="chat-welcome" aria-label="Get started">
            <h2 className="chat-welcome__title">
              Welcome to the Office assistant
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

      {userRole === "admin" ? (
        <DocumentUploadPanel
          onUnauthenticated={onUnauthenticated}
        />
      ) : null}

      {userRole === "admin" ? (
        <label className="chat__type-filter">
          Search document type

          <select
            aria-label="Search document type"
            disabled={isLoading}
            onChange={(event) =>
              setDocumentType(
                event.target.value as DocumentType | "",
              )
            }
            value={documentType}
          >
            <option value="">All types</option>

            {DOCUMENT_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <ChatComposer
        isLoading={isLoading}
        onAsk={(question) => {
          void handleAsk(question);
        }}
      />

      <RecentChatsDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onSelectChat={(chatId) => {
          void handleSelectSavedChat(chatId);
        }}
      />
    </main>
  );
}