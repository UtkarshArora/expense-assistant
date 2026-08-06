import { useCallback, useEffect, useState } from "react"

import { ConversationSidebar } from "@/components/ConversationSidebar"
import { ChatView } from "@/components/ChatView"
import { getConversation, listConversations, sendMessage } from "@/api"
import type { Conversation, Message } from "@/api"

function App() {
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
        conversations={conversations}
        activeId={activeId}
        onSelect={handleSelect}
        onNewChat={handleNewChat}
      />
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-14 shrink-0 items-center border-b px-6">
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
