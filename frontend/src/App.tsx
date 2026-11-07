import { useAuth0 } from "@auth0/auth0-react"

import { ChatApp } from "@/ChatApp"
import { LoginPage } from "@/components/LoginPage"

/** Auth gate: the chat UI only renders for a signed-in user. */
function App() {
  const { isLoading, isAuthenticated, error } = useAuth0()

  if (isLoading) {
    return (
      <div className="flex h-svh items-center justify-center bg-background text-sm text-muted-foreground">
        Loading…
      </div>
    )
  }
  if (!isAuthenticated) return <LoginPage error={error} />
  return <ChatApp />
}

export default App
