import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent, PointerEvent, ReactNode, RefObject } from "react";
import { RecentChatsDrawer } from "./RecentChatsDrawer";
import { ShellIcon } from "./ShellIcon";

const MIN_WIDTH = 240;
const DEFAULT_WIDTH = 290;
const MAX_WIDTH = 420;
const MOBILE_BREAKPOINT = 760;
const WIDTH_KEY = "oiap.sidebar_width";

function clampWidth(width: number) {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(width)));
}

function loadWidth() {
  try {
    const saved = localStorage.getItem(WIDTH_KEY);
    if (saved?.trim() && Number.isFinite(Number(saved))) return clampWidth(Number(saved));
  } catch { /* Storage can be unavailable; resizing still works for this session. */ }
  return DEFAULT_WIDTH;
}

interface Props {
  sidebarRef: RefObject<HTMLElement | null>;
  isOpen: boolean;
  eventsOpen: boolean;
  busy: boolean;
  activeChatId: string | null;
  historyRefresh: number;
  onClose: () => void;
  onOpenEvents: () => void;
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  events: ReactNode;
  footer: ReactNode;
}

export function Sidebar({ sidebarRef, isOpen, eventsOpen, busy, activeChatId, historyRefresh,
  onClose, onOpenEvents, onNewChat, onSelectChat, events, footer }: Props) {
  const [width, setWidth] = useState(loadWidth);
  const [isDesktop, setIsDesktop] = useState(() => window.innerWidth > MOBILE_BREAKPOINT);
  const [resizing, setResizing] = useState(false);
  const drag = useRef<{ pointerId: number; startX: number; startWidth: number; handle: HTMLDivElement } | null>(null);

  useEffect(() => {
    try { localStorage.setItem(WIDTH_KEY, String(width)); }
    catch { /* A local UI preference must never prevent using the sidebar. */ }
  }, [width]);

  const stopResizing = useCallback(() => {
    const active = drag.current;
    if (!active) return;
    drag.current = null;
    setResizing(false);
    document.body.classList.remove("assistant-sidebar-resizing");
    if (active.handle.hasPointerCapture(active.pointerId)) active.handle.releasePointerCapture(active.pointerId);
  }, []);

  useEffect(() => {
    function viewportChanged() {
      const desktop = window.innerWidth > MOBILE_BREAKPOINT;
      setIsDesktop(desktop);
      if (!desktop) stopResizing();
    }
    window.addEventListener("resize", viewportChanged);
    window.addEventListener("blur", stopResizing);
    return () => {
      window.removeEventListener("resize", viewportChanged);
      window.removeEventListener("blur", stopResizing);
      stopResizing();
    };
  }, [stopResizing]);

  function startResizing(event: PointerEvent<HTMLDivElement>) {
    if (window.innerWidth <= MOBILE_BREAKPOINT || event.button !== 0 || !event.isPrimary || drag.current) return;
    event.preventDefault();
    event.currentTarget.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { pointerId: event.pointerId, startX: event.clientX, startWidth: width, handle: event.currentTarget };
    setResizing(true);
    document.body.classList.add("assistant-sidebar-resizing");
  }

  function resize(event: PointerEvent<HTMLDivElement>) {
    const active = drag.current;
    if (!active || event.pointerId !== active.pointerId) return;
    event.preventDefault();
    setWidth(clampWidth(active.startWidth + event.clientX - active.startX));
  }

  function finishResizing(event: PointerEvent<HTMLDivElement>) {
    if (event.pointerId === drag.current?.pointerId) stopResizing();
  }

  function resizeWithKeyboard(event: KeyboardEvent<HTMLDivElement>) {
    if (window.innerWidth <= MOBILE_BREAKPOINT) return;
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    setWidth((previous) => clampWidth(previous + (event.key === "ArrowRight" ? 10 : -10)));
  }

  return <aside ref={sidebarRef} id="assistant-sidebar"
    className={`assistant-sidebar${isOpen ? " is-open" : ""}${resizing ? " is-resizing" : ""}`}
    style={{ "--sidebar-width": `${width}px` } as CSSProperties}
    aria-label="Office Assistant sidebar">
    <div className="assistant-sidebar__brand"><strong>Office Assistant</strong>
      <button type="button" className="shell-icon-button assistant-sidebar__close" aria-label="Close sidebar" onClick={onClose}>
        <ShellIcon name="close" />
      </button>
    </div>
    <nav className="assistant-sidebar__actions" aria-label="Assistant navigation">
      <button type="button" className="assistant-sidebar__action" disabled={busy} onClick={onNewChat}>
        <ShellIcon name="new-chat" />New Chat
      </button>
      <button type="button" className="assistant-sidebar__action" aria-expanded={eventsOpen}
        aria-controls="sidebar-events" onClick={onOpenEvents}>
        <ShellIcon name="calendar" />Events
        <span className="assistant-sidebar__chevron"><ShellIcon name="chevron" /></span>
      </button>
    </nav>
    <div className="assistant-sidebar__middle">
      {events}
      <RecentChatsDrawer variant="sidebar" isOpen refreshKey={historyRefresh} activeChatId={activeChatId}
        disabled={busy} onClose={onClose} onSelectChat={onSelectChat} />
    </div>
    <div className="assistant-sidebar__footer">{footer}</div>
    <div className="assistant-sidebar__resize" role="separator" tabIndex={0} hidden={!isDesktop}
      aria-label="Resize sidebar" aria-orientation="vertical" aria-controls="assistant-sidebar"
      aria-valuemin={MIN_WIDTH} aria-valuemax={MAX_WIDTH} aria-valuenow={width} aria-valuetext={`${width} pixels`}
      onPointerDown={startResizing} onPointerMove={resize} onPointerUp={finishResizing}
      onPointerCancel={finishResizing} onLostPointerCapture={finishResizing} onKeyDown={resizeWithKeyboard} />
  </aside>;
}
