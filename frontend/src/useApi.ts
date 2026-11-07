import { useMemo } from "react"
import { useAuth0 } from "@auth0/auth0-react"

import { createApi, type Api } from "@/api"

/** The API client, authenticated with the signed-in user's access token. */
export function useApi(): Api {
  const { getAccessTokenSilently } = useAuth0()
  // getAccessTokenSilently is stable, so the client is created once.
  return useMemo(() => createApi(() => getAccessTokenSilently()), [getAccessTokenSilently])
}
