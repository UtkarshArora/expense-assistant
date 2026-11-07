import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { cn } from "@/lib/utils"
import { ToolCallTrace } from "@/components/ToolCallTrace"
import type { Message } from "@/api"

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user"

  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "flex max-w-[75%] flex-col",
          isUser ? "items-end" : "items-start"
        )}
      >
        {!isUser && <ToolCallTrace toolCalls={message.tool_calls} />}
        {!isUser && message.truncated && (
          <span className="mb-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-400">
            Partial answer: step limit reached
          </span>
        )}
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
            isUser
              ? "whitespace-pre-wrap bg-primary text-primary-foreground"
              : "md bg-muted text-foreground"
          )}
        >
          {isUser ? (
            message.content
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          )}
        </div>
      </div>
    </div>
  )
}
