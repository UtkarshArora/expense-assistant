import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import './index.css'
import App from './App.tsx'

const domain = import.meta.env.VITE_AUTH0_DOMAIN
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID
const audience = import.meta.env.VITE_AUTH0_AUDIENCE

const root = createRoot(document.getElementById('root')!)

if (!domain || !clientId || !audience) {
  root.render(
    <p style={{ padding: 24, fontFamily: 'system-ui' }}>
      Missing Auth0 config. Set VITE_AUTH0_DOMAIN, VITE_AUTH0_CLIENT_ID and
      VITE_AUTH0_AUDIENCE in frontend/.env.local (see frontend/.env.example).
    </p>,
  )
} else {
  root.render(
    <StrictMode>
      <Auth0Provider
        domain={domain}
        clientId={clientId}
        authorizationParams={{ audience, redirect_uri: window.location.origin }}
        // Refresh tokens kept in localStorage so a reload doesn't depend on
        // third-party cookies (blocked by Safari/Brave). Trade-off: a script
        // injected via XSS could read them; rotation limits the damage.
        useRefreshTokens
        cacheLocation="localstorage"
      >
        <App />
      </Auth0Provider>
    </StrictMode>,
  )
}
