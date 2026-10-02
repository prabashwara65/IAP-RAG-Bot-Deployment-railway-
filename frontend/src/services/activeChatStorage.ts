import type { ChatTurn } from "../components/ChatMessage";

const STORAGE_PREFIX = "oiap_active_chat_";

export function loadActiveChat(userId: string): ChatTurn[] {
  try {
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${userId}`);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed as ChatTurn[];
    }
    return [];
  } catch {
    return [];
  }
}

export function saveActiveChat(userId: string, turns: ChatTurn[]): void {
  try {
    if (turns.length === 0) {
      localStorage.removeItem(`${STORAGE_PREFIX}${userId}`);
    } else {
      localStorage.setItem(`${STORAGE_PREFIX}${userId}`, JSON.stringify(turns));
    }
  } catch {
    // Ignore storage quota errors
  }
}

export function clearActiveChat(userId: string): void {
  try {
    localStorage.removeItem(`${STORAGE_PREFIX}${userId}`);
  } catch {
    // Ignore
  }
}
