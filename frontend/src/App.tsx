import { useCallback, useEffect, useState } from "react"
import { MessageSquarePlus, PanelLeftClose, PanelLeftOpen } from "lucide-react"

import { ConversationSidebar } from "@/components/ConversationSidebar"
import { ChatView } from "@/components/ChatView"
import { Button } from "@/components/ui/button"
import { getConversation, listConversations, sendMessage } from "@/api"
import type { Conversation, Message } from "@/api"

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

function App() {
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
      console.error(e)
    }
  }, [])

  useEffect(() => {
    refreshConversations()
  }, [refreshConversations])

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
    } catch {
      setError("Failed to load conversation.")
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
      setError(e instanceof Error ? e.message : "Something went wrong.")
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

export default App
