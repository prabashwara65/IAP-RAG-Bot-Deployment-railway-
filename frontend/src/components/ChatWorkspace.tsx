import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { askHrQuestion, HrAskError } from "../api/hrRag";
import type { HrAskFailureKind } from "../api/hrRag";
import { ChatComposer } from "./ChatComposer";
import { ChatMessage } from "./ChatMessage";
import type { ChatTurn } from "./ChatMessage";
import { ErrorNotice } from "./ErrorNotice";
import { DocumentUploadPanel } from "./DocumentUploadPanel";
import { DOCUMENT_TYPES } from "../api/documents";
import type { DocumentType } from "../api/documents";
import type { Profile, ThemePreference, UserRole } from "../api/auth";
import { getSavedChat, saveChatSession } from "../api/savedChats";
import { Sidebar } from "./Sidebar";
import { SidebarAccountMenu } from "./SidebarAccountMenu";
import { ShellIcon } from "./ShellIcon";
import "../chat-shell.css";
import { EventsDrawer } from "./EventsDrawer";
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
  user?: Profile;
  avatarUrl?: string | null;
  content?: ReactNode;
  onOpenChat?: () => void;
  onOpenProfile?: () => void;
  onOpenUsers?: () => void;
  onThemeChange?: (theme: ThemePreference) => void;
  onLogout?: () => void;
}

export function ChatWorkspace({
  onUnauthenticated,
  userId = "default",
  userRole,
  user,
  avatarUrl = null,
  content,
  onOpenChat = () => {},
  onOpenProfile = () => {},
  onOpenUsers = () => {},
  onThemeChange = () => {},
  onLogout = () => {},
}: ChatWorkspaceProps) {
  const [turns, setTurns] = useState<ChatTurn[]>(() => loadActiveChat(userId));
  const [isLoading, setIsLoading] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [documentType, setDocumentType] = useState<DocumentType | "">("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const sidebarRef = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const [eventsOpen, setEventsOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveToast, setSaveToast] = useState<string | null>(null);

  const transcriptRef = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const showingOtherContent = content !== undefined;
  const nextTurnId = useRef(turns.length);

  // Sync active ongoing turns with browser local storage on every update
  useEffect(() => {
    saveActiveChat(userId, turns);
  }, [turns, userId]);

  useLayoutEffect(() => {
    const transcript = transcriptRef.current;
    if (transcript && !showingOtherContent && followLatest.current) {
      // Scroll this region only; never move the app shell or the browser page.
      transcript.scrollTop = transcript.scrollHeight;
    }
  }, [turns, isLoading, failure, showingOtherContent]);

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (!transcript || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (!showingOtherContent && followLatest.current) transcript.scrollTop = transcript.scrollHeight;
    });
    observer.observe(transcript);
    return () => observer.disconnect();
  }, [showingOtherContent]);

  function handleTranscriptScroll() {
    const transcript = transcriptRef.current;
    if (transcript) {
      followLatest.current = transcript.scrollHeight - transcript.clientHeight - transcript.scrollTop <= 64;
    }
  }

  function closeSidebar() {
    setSidebarOpen(false);
    if (sidebarOpen) menuButton.current?.focus();
  }

  useEffect(() => {
    function handleResize() {
      if (window.innerWidth > 760) setSidebarOpen(false);
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    if (!sidebarOpen) return;
    const element = sidebarRef.current;
    element?.querySelector<HTMLButtonElement>(".assistant-sidebar__close")?.focus();
    function keyboard(event: KeyboardEvent) {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        setSidebarOpen(false);
        menuButton.current?.focus();
      }
      if (event.key !== "Tab" || !element) return;
      const buttons = Array.from(element.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]'))
        .filter((button) => !button.closest("[hidden]"));
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener("keydown", keyboard);
    return () => document.removeEventListener("keydown", keyboard);
  }, [sidebarOpen]);

  function navigate(action: () => void) { closeSidebar(); action(); }

  function createTurnId(): string {
    nextTurnId.current += 1;
    return `turn-${Date.now()}-${nextTurnId.current}`;
  }

  function handleNewChat() {
    followLatest.current = true;
    setTurns([]);
    setFailure(null);
    clearActiveChat(userId);
    setSaveToast(null);
    setActiveChatId(null);
    navigate(onOpenChat);
  }

  async function handleSaveChat() {
    if (turns.length === 0 || isSaving) return;

    setIsSaving(true);
    setSaveToast(null);

    try {
      await saveChatSession(turns);
      setSaveToast("Chat saved to account!");
      setHistoryRefresh((previous) => previous + 1);
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

      followLatest.current = true;
      setTurns(detail.messages);
      setActiveChatId(chatId);
      saveActiveChat(userId, detail.messages);
      navigate(onOpenChat);
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

    followLatest.current = true;
    setFailure(null);
    setActiveChatId(null);

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
    <div className="assistant-shell">
      {sidebarOpen ? <button type="button" className="assistant-sidebar-backdrop" aria-label="Close navigation"
        onClick={closeSidebar} /> : null}
      <Sidebar sidebarRef={sidebarRef} isOpen={sidebarOpen} eventsOpen={eventsOpen} busy={isLoading}
        activeChatId={activeChatId} historyRefresh={historyRefresh} onClose={closeSidebar}
        onOpenEvents={() => setEventsOpen((open) => !open)} onNewChat={handleNewChat}
        events={<EventsDrawer isOpen={eventsOpen} onUnauthenticated={onUnauthenticated} />}
        onSelectChat={(chatId) => void handleSelectSavedChat(chatId)}
        footer={user ? <SidebarAccountMenu user={user} avatarUrl={avatarUrl} onThemeChange={onThemeChange}
          onOpenProfile={() => navigate(onOpenProfile)} onOpenUsers={() => navigate(onOpenUsers)}
          onLogout={() => navigate(onLogout)} /> : null} />
      <div className="assistant-content">
        <main className="assistant-main" inert={sidebarOpen}>
          <header className="assistant-header">
            <button type="button" className="shell-icon-button assistant-header__menu" ref={menuButton}
              aria-label="Open sidebar" aria-expanded={sidebarOpen} aria-controls="assistant-sidebar"
              onClick={() => setSidebarOpen(true)}><ShellIcon name="menu" /></button>
            {content !== undefined ? <button type="button" className="shell-save" onClick={onOpenChat}>Back to chat</button> : null}
          </header>
          {saveToast ? <p className="shell-toast" role="status">{saveToast}</p> : null}
          <section className={"chat shell-chat" + (turns.length === 0 ? " shell-chat--empty" : "")}
            hidden={content !== undefined} aria-label="Assistant conversation">
            <div className="chat__transcript" role="log" aria-label="Conversation"
              ref={transcriptRef} onScroll={handleTranscriptScroll}>
              {turns.length === 0 ? <section className="chat-welcome" aria-label="Get started">
                <span className="assistant-mark assistant-mark--welcome"><ShellIcon name="assistant" /></span>
                <h2 className="chat-welcome__title">How can I help{user?.display_name ? ", " + user.display_name : ""}?</h2>
                <p className="chat-welcome__description">Answers come only from approved company documents, with sources.</p>
              </section> : null}
              {turns.map((turn) => <ChatMessage key={turn.id} turn={turn} />)}
              {isLoading ? <p className="message message--pending" role="status">Searching approved HR sources&hellip;</p> : null}
              {failure === null ? null : <ErrorNotice correlationId={failure.correlationId} kind={failure.kind} />}
            </div>
            <div className="shell-chat__bottom">
              {turns.length > 0 ? <div className="shell-chat__actions">
                <button type="button" className="shell-save" disabled={isSaving || isLoading}
                  onClick={() => void handleSaveChat()}><ShellIcon name="save" />{isSaving ? "Saving…" : "Save Chat"}</button>
              </div> : null}
              <ChatComposer isLoading={isLoading} onAsk={(question) => void handleAsk(question)} />
              {turns.length === 0 ? <div className="chat-suggestions" aria-label="Suggested questions">
                {[
                  ["Annual leave", "How many days of annual leave do I get?"],
                  ["Remote work", "What is the remote work policy?"],
                  ["Expense claims", "How do I submit an expense claim?"],
                  ["Probation", "How long is the probation period?"],
                ].map(([label, question]) => <button type="button" key={label} disabled={isLoading}
                  onClick={() => void handleAsk(question!)}>{label}</button>)}
              </div> : null}
              {userRole === "admin" ? <details className="shell-documents">
                <summary>Documents</summary>
                <DocumentUploadPanel onUnauthenticated={onUnauthenticated} />
                <label className="chat__type-filter">Search document type
                  <select aria-label="Search document type" disabled={isLoading}
                    value={documentType} onChange={(event) => setDocumentType(event.target.value as DocumentType | "")}>
                    <option value="">All types</option>
                    {DOCUMENT_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
                  </select>
                </label>
              </details> : null}
            </div>
          </section>
          {content !== undefined ? <div className="shell-screen">{content}</div> : null}
          <footer className="assistant-footer">Answers are generated only from documents approved for retrieval.
            Always confirm anything consequential with your team.</footer>
        </main>
      </div>
    </div>
  );
}
