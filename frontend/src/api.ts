const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

export interface ToolCall {
  id: string
  name: string
  input: Record<string, unknown>
  output: string
  created_at: string
}

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  created_at: string
  tool_calls: ToolCall[]
}

export interface ChatResponse {
  conversation_id: string
  message: Message
}

export interface Conversation {
  id: string
  title: string
  created_at: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ""}`)
  }
  return res.json() as Promise<T>
}

export function sendMessage(
  message: string,
  conversationId: string | null
): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ message, conversation_id: conversationId }),
  })
}

export function listConversations(): Promise<Conversation[]> {
  return request<Conversation[]>("/conversations")
}

export function getConversation(id: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/conversations/${id}`)
}
