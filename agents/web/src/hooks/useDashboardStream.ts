import { useEffect } from 'react'
import { useConsoleStore } from '@/store/useConsoleStore'
import type { AgentRole, HistoryResponse, OverviewResponse } from '@/types/console'

const HISTORY_ROLES: AgentRole[] = ['proposer', 'reviewer', 'resolver', 'trader']

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export function useDashboardStream(selectedRole: AgentRole | 'all') {
  const addEvent = useConsoleStore((state) => state.addEvent)
  const hydrateEvents = useConsoleStore((state) => state.hydrateEvents)
  const hydrateOverview = useConsoleStore((state) => state.hydrateOverview)
  const setConnected = useConsoleStore((state) => state.setConnected)

  useEffect(() => {
    let closed = false
    let source: EventSource | null = null

    async function bootstrap() {
      try {
        const overview = await fetchJson<OverviewResponse>('/api/overview')
        if (!closed) {
          hydrateOverview(overview)
        }
        const rolesToLoad = selectedRole === 'all' ? HISTORY_ROLES : [selectedRole]
        const histories = await Promise.all(
          rolesToLoad.map(async (role) => ({
            role,
            payload: await fetchJson<HistoryResponse>(`/api/history?role=${role}&limit=160&offset=0`),
          })),
        )
        if (!closed) {
          for (const item of histories) {
            hydrateEvents(item.role, item.payload.events)
          }
        }
      } catch (error) {
        console.error(error)
      }
    }

    bootstrap().catch(console.error)
    source = new EventSource(`/api/stream?role=${selectedRole}`)
    source.onopen = () => setConnected(true)
    source.onerror = () => setConnected(false)
    source.onmessage = (event) => {
      try {
        addEvent(JSON.parse(event.data))
      } catch (error) {
        console.error(error)
      }
    }

    return () => {
      closed = true
      setConnected(false)
      source?.close()
    }
  }, [addEvent, hydrateEvents, hydrateOverview, selectedRole, setConnected])
}
