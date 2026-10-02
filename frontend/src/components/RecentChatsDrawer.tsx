import { useEffect, useState } from "react";
import { deleteSavedChat, listSavedChats } from "../api/savedChats";
import type { SavedChatSummary } from "../api/savedChats";

interface RecentChatsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectChat: (chatId: string) => void;
}

export function RecentChatsDrawer({
  isOpen,
  onClose,
  onSelectChat,
}: RecentChatsDrawerProps) {
  const [chats, setChats] = useState<SavedChatSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    let cancelled = false;
    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const items = await listSavedChats();
        if (!cancelled) {
          setChats(items);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load chats");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  async function handleDelete(event: React.MouseEvent, chatId: string) {
    event.stopPropagation();
    try {
      await deleteSavedChat(chatId);
      setChats((prev) => prev.filter((c) => c.id !== chatId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete chat");
    }
  }

  function formatDate(iso: string): string {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return iso;
    }
  }

  if (!isOpen) return null;

  return (
    <div
      className="recent-chats-backdrop"
      onClick={onClose}
      role="presentation"
    >
      <aside
        className="recent-chats-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Recent Saved Chats"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="recent-chats-drawer__header">
          <div className="recent-chats-drawer__title-group">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            <h2>Recent Chats</h2>
          </div>
          <button
            type="button"
            className="recent-chats-drawer__close"
            onClick={onClose}
            aria-label="Close recent chats"
          >
            ✕
          </button>
        </div>

        {error ? (
          <div className="recent-chats-drawer__error" role="alert">
            {error}
          </div>
        ) : null}

        <div className="recent-chats-drawer__body">
          {isLoading ? (
            <div className="recent-chats-drawer__status">Loading saved chats&hellip;</div>
          ) : chats.length === 0 ? (
            <div className="recent-chats-drawer__empty">
              <p>No saved chats yet.</p>
              <span>Click "Save Chat" during any conversation to save it to your account.</span>
            </div>
          ) : (
            <ul className="recent-chats-list">
              {chats.map((chat) => (
                <li key={chat.id}>
                  <button
                    type="button"
                    className="recent-chat-item"
                    onClick={() => {
                      onSelectChat(chat.id);
                      onClose();
                    }}
                  >
                    <div className="recent-chat-item__content">
                      <span className="recent-chat-item__title" title={chat.title}>
                        {chat.title}
                      </span>
                      <span className="recent-chat-item__meta">
                        {formatDate(chat.updated_at)} &bull; {chat.message_count} {chat.message_count === 1 ? "turn" : "turns"}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="recent-chat-item__delete"
                      onClick={(e) => void handleDelete(e, chat.id)}
                      title="Delete saved chat"
                      aria-label={`Delete ${chat.title}`}
                    >
                      <svg
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                      </svg>
                    </button>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}
