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
  /** The agent hit its step limit; the reply may be partial. */
  truncated: boolean
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

export interface Me {
  id: string
  email: string | null
  display_name: string | null
  role: "employee" | "manager" | "admin"
  department: string | null
  employee_name: string | null
}

/** The backend rejected the access token (expired, revoked, or missing). */
export class UnauthorizedError extends Error {}

/** A request failed with a non-2xx status; `detail` is FastAPI's message. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export type GetToken = () => Promise<string | undefined>

/**
 * API client bound to a token getter (Auth0's getAccessTokenSilently).
 * Every request sends `Authorization: Bearer <access token>`.
 */
export function createApi(getToken: GetToken) {
  async function request<T>(path: string, options?: RequestInit): Promise<T> {
    let token: string | undefined
    try {
      token = await getToken()
    } catch {
      token = undefined // e.g. login_required: the refresh token is gone
    }
    if (!token) throw new UnauthorizedError("Your session has expired.")
    const res = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    })
    if (res.status === 401) throw new UnauthorizedError("Your session has expired.")
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      const detail = typeof body?.detail === "string" ? body.detail : res.statusText
      throw new ApiError(res.status, detail)
    }
    return res.json() as Promise<T>
  }

  return {
    getMe: () => request<Me>("/me"),

    sendMessage: (message: string, conversationId: string | null) =>
      request<ChatResponse>("/chat", {
        method: "POST",
        body: JSON.stringify({ message, conversation_id: conversationId }),
      }),

    listConversations: () => request<Conversation[]>("/conversations"),

    getConversation: (id: string) =>
      request<ConversationDetail>(`/conversations/${id}`),
  }
}

export type Api = ReturnType<typeof createApi>
