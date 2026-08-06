import { useState } from "react"
import { ChevronRight, Wrench } from "lucide-react"

import { cn } from "@/lib/utils"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import type { ToolCall } from "@/api"

export function ToolCallTrace({ toolCalls }: { toolCalls: ToolCall[] }) {
  const [open, setOpen] = useState(false)

  if (toolCalls.length === 0) return null

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mb-2 w-full">
      <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
        <ChevronRight
          className={cn("size-3.5 transition-transform", open && "rotate-90")}
        />
        <Wrench className="size-3.5" />
        {toolCalls.length} tool call{toolCalls.length === 1 ? "" : "s"}
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2 flex flex-col gap-2 border-l-2 border-border pl-3">
        {toolCalls.map((tc) => (
          <div key={tc.id} className="rounded-md border bg-muted/40 p-2 text-xs">
            <div className="font-mono font-semibold break-all">
              {tc.name}({JSON.stringify(tc.input)})
            </div>
            <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all text-muted-foreground">
              {tc.output}
            </pre>
          </div>
        ))}
      </CollapsibleContent>
    </Collapsible>
  )
}
