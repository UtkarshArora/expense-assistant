import { useState, type FormEvent } from "react"
import { Send } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { MessageList } from "@/components/MessageList"
import type { Message } from "@/api"

interface Props {
  messages: Message[]
  pending: boolean
  onSend: (message: string) => void
}

export function ChatView({ messages, pending, onSend }: Props) {
  const [input, setInput] = useState("")

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = input.trim()
    if (!trimmed || pending) return
    onSend(trimmed)
    setInput("")
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <MessageList messages={messages} pending={pending} />
      <form onSubmit={handleSubmit} className="border-t p-4">
        <div className="mx-auto flex max-w-3xl gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about company spending or policy..."
            disabled={pending}
            autoFocus
          />
          <Button type="submit" size="icon" disabled={pending || !input.trim()}>
            <Send className="size-4" />
          </Button>
        </div>
      </form>
    </div>
  )
}
