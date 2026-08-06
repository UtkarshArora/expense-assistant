import { useEffect, useRef } from "react"

import { ScrollArea } from "@/components/ui/scroll-area"
import { MessageBubble } from "@/components/MessageBubble"
import type { Message } from "@/api"

export function MessageList({
  messages,
  pending,
}: {
  messages: Message[]
  pending: boolean
}) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, pending])

  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="mx-auto flex max-w-3xl flex-col gap-4 p-6">
        {messages.length === 0 && !pending && (
          <div className="mt-20 text-center text-sm text-muted-foreground">
            Ask about company spending — e.g. "What client meals did Sales
            have last quarter, and were any over the policy cap?"
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        {pending && (
          <div className="flex justify-start">
            <div className="rounded-2xl bg-muted px-4 py-2.5 text-sm text-muted-foreground">
              Thinking…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  )
}
