import { useCallback, useEffect, useState } from "react"
import { useAuth0 } from "@auth0/auth0-react"
import { LogOut, MessageSquarePlus, PanelLeftClose, PanelLeftOpen } from "lucide-react"

import { ConversationSidebar } from "@/components/ConversationSidebar"
import { ChatView } from "@/components/ChatView"
import { Button } from "@/components/ui/button"
import { UnauthorizedError } from "@/api"
import type { Conversation, Me, Message } from "@/api"
import { useApi } from "@/useApi"

const SIDEBAR_KEY = "sidebar-open"

// Saved choice wins; otherwise start open on desktop, closed on narrow screens.
function initialSidebarOpen(): boolean {
  try {
    const saved = localStorage.getItem(SIDEBAR_KEY)
    if (saved !== null) return saved === "true"
  } catch {
    // storage unavailable (private mode, blocked site data)
  }
  return window.matchMedia("(min-width: 768px)").matches
}

const ROLE_LABELS: Record<Me["role"], string> = {
  employee: "Employee",
  manager: "Manager",
  admin: "Admin",
}

function errorMessage(e: unknown, fallback: string): string {
  if (e instanceof UnauthorizedError) return "Your session has expired. Sign out and sign in again."
  return e instanceof Error ? e.message : fallback
}

export function ChatApp() {
  const { logout } = useAuth0()
  const { getMe, getConversation, listConversations, sendMessage } = useApi()
  const [me, setMe] = useState<Me | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(initialSidebarOpen)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await listConversations())
    } catch (e) {
      setError(errorMessage(e, "Failed to load conversations."))
    }
  }, [listConversations])

  useEffect(() => {
    refreshConversations()
  }, [refreshConversations])

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch((e) => setError(errorMessage(e, "Failed to load your profile.")))
  }, [getMe])

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, String(sidebarOpen))
    } catch {
      // non-essential preference
    }
  }, [sidebarOpen])

  // Cmd+B / Ctrl+B toggles the sidebar.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "b") {
        e.preventDefault()
        setSidebarOpen((open) => !open)
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])

  async function handleSelect(id: string) {
    setActiveId(id)
    setError(null)
    try {
      const detail = await getConversation(id)
      setMessages(detail.messages)
    } catch (e) {
      setError(errorMessage(e, "Failed to load conversation."))
    }
  }

  function handleNewChat() {
    setActiveId(null)
    setMessages([])
    setError(null)
  }

  async function handleSend(text: string) {
    setError(null)
    const optimisticUser: Message = {
      id: `local-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
      truncated: false,
      tool_calls: [],
    }
    setMessages((prev) => [...prev, optimisticUser])
    setPending(true)
    try {
      const res = await sendMessage(text, activeId)
      setMessages((prev) => [...prev, res.message])
      const wasNew = activeId === null
      setActiveId(res.conversation_id)
      if (wasNew) {
        await refreshConversations()
      }
    } catch (e) {
      setError(errorMessage(e, "Something went wrong."))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex h-svh w-full overflow-hidden bg-background text-foreground">
      <ConversationSidebar
        open={sidebarOpen}
        conversations={conversations}
        activeId={activeId}
        onSelect={handleSelect}
        onNewChat={handleNewChat}
      />
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSidebarOpen((open) => !open)}
            aria-controls="conversation-sidebar"
            aria-expanded={sidebarOpen}
            aria-label={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
            title={`${sidebarOpen ? "Hide" : "Show"} sidebar (⌘B / Ctrl+B)`}
          >
            {sidebarOpen ? <PanelLeftClose /> : <PanelLeftOpen />}
          </Button>
          {!sidebarOpen && (
            <Button
              variant="ghost"
              size="icon"
              onClick={handleNewChat}
              aria-label="New chat"
              title="New chat"
            >
              <MessageSquarePlus />
            </Button>
          )}
          <h1 className="text-sm font-semibold">Expense Assistant</h1>
          <div className="ml-auto flex items-center gap-3">
            {me && (
              <div className="flex items-center gap-2 text-sm">
                <span className="hidden text-muted-foreground sm:inline">
                  {me.display_name ?? me.email}
                </span>
                <span className="rounded-full border px-2 py-0.5 text-xs font-medium">
                  {ROLE_LABELS[me.role]}
                  {me.department ? ` · ${me.department}` : ""}
                </span>
              </div>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut />
            </Button>
          </div>
        </header>
        {error && (
          <div className="border-b bg-destructive/10 px-6 py-2 text-sm text-destructive">
            {error}
          </div>
        )}
        <ChatView messages={messages} pending={pending} onSend={handleSend} />
      </div>
    </div>
  )
}
