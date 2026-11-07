import { useAuth0 } from "@auth0/auth0-react"
import { LogIn } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

interface DemoAccount {
  label: string
  email: string
  password: string
}

/**
 * Demo credentials for reviewers, from VITE_DEMO_ACCOUNTS. They are bundled
 * into the public JS on purpose, so use passwords that exist nowhere else.
 */
function demoAccounts(): DemoAccount[] {
  const raw = import.meta.env.VITE_DEMO_ACCOUNTS
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed)
      ? parsed.filter(
          (a): a is DemoAccount =>
            typeof a?.label === "string" &&
            typeof a?.email === "string" &&
            typeof a?.password === "string"
        )
      : []
  } catch {
    return []
  }
}

export function LoginPage({ error }: { error?: Error }) {
  const { loginWithRedirect } = useAuth0()
  const accounts = demoAccounts()

  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-4 py-10 text-foreground">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Expense Assistant</CardTitle>
          <CardDescription>
            Ask about company spending and expense policy. Access is
            invite-only, and what you can see depends on your role.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {error && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error.message}
            </p>
          )}
          <Button onClick={() => loginWithRedirect()} className="w-full">
            <LogIn />
            Sign in
          </Button>
        </CardContent>
        {accounts.length > 0 && (
          <CardFooter className="flex flex-col items-stretch gap-2 border-t pt-6">
            <p className="text-sm font-medium">Demo accounts</p>
            <ul className="flex flex-col gap-2 text-sm">
              {accounts.map((a) => (
                <li key={a.email} className="rounded-md border px-3 py-2">
                  <div className="font-medium">{a.label}</div>
                  <div className="font-mono text-xs text-muted-foreground break-all">
                    {a.email} / {a.password}
                  </div>
                </li>
              ))}
            </ul>
          </CardFooter>
        )}
      </Card>
    </div>
  )
}
