import { apiBaseUrl, authHeaders, jsonHeaders } from "./http";
import type { ChatTurn } from "../components/ChatMessage";

export interface SavedChatSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface SavedChatDetail {
  id: string;
  title: string;
  messages: ChatTurn[];
  created_at: string;
  updated_at: string;
}

export async function saveChatSession(
  turns: ChatTurn[],
  title?: string,
): Promise<SavedChatSummary> {
  const url = `${apiBaseUrl()}/api/v1/chats`;
  const response = await fetch(url, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      title: title || undefined,
      messages: turns,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to save chat: ${response.statusText}`);
  }

  return (await response.json()) as SavedChatSummary;
}

export async function listSavedChats(): Promise<SavedChatSummary[]> {
  const url = `${apiBaseUrl()}/api/v1/chats`;
  const response = await fetch(url, {
    method: "GET",
    headers: authHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch saved chats: ${response.statusText}`);
  }

  return (await response.json()) as SavedChatSummary[];
}

export async function getSavedChat(chatId: string): Promise<SavedChatDetail> {
  const url = `${apiBaseUrl()}/api/v1/chats/${encodeURIComponent(chatId)}`;
  const response = await fetch(url, {
    method: "GET",
    headers: authHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch chat details: ${response.statusText}`);
  }

  return (await response.json()) as SavedChatDetail;
}

export async function deleteSavedChat(chatId: string): Promise<void> {
  const url = `${apiBaseUrl()}/api/v1/chats/${encodeURIComponent(chatId)}`;
  const response = await fetch(url, {
    method: "DELETE",
    headers: authHeaders(),
  });

  if (!response.ok && response.status !== 404) {
    throw new Error(`Failed to delete chat: ${response.statusText}`);
  }
}
