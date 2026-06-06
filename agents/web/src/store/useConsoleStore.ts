import { create } from 'zustand'
import type { AgentEvent, AgentRole, ConsoleSummary, OverviewResponse, RoleSummary, WorkspaceItem } from '@/types/console'

const HISTORY_STORAGE_KEY = 'entromarket-console-history-v2'
const ROLE_KEYS: AgentRole[] = ['proposer', 'reviewer', 'resolver', 'trader']

type EventsByRole = Record<AgentRole, AgentEvent[]>

type ConsoleState = {
  selectedRole: AgentRole | 'all'
  connected: boolean
  summary: ConsoleSummary | null
  statuses: RoleSummary[]
  workspace: WorkspaceItem[]
  events: AgentEvent[]
  eventsByRole: EventsByRole
  setSelectedRole: (role: AgentRole | 'all') => void
  setConnected: (value: boolean) => void
  hydrateOverview: (payload: OverviewResponse) => void
  hydrateEvents: (role: AgentRole | 'all', events: AgentEvent[]) => void
  addEvent: (event: AgentEvent) => void
}

function emptyEventsByRole(): EventsByRole {
  return {
    proposer: [],
    reviewer: [],
    resolver: [],
    trader: [],
  }
}

function flattenEventsByRole(eventsByRole: EventsByRole): AgentEvent[] {
  return mergeEvents(...ROLE_KEYS.map((role) => eventsByRole[role]))
}

function loadStoredEventsByRole(): EventsByRole {
  if (typeof window === 'undefined') {
    return emptyEventsByRole()
  }
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY)
    if (!raw) {
      return emptyEventsByRole()
    }
    const parsed = JSON.parse(raw)
    if (!isObject(parsed)) {
      return emptyEventsByRole()
    }
    const next = emptyEventsByRole()
    for (const role of ROLE_KEYS) {
      const items = parsed[role]
      if (Array.isArray(items)) {
        next[role] = items.filter(isAgentEventLike)
      }
    }
    return next
  } catch {
    return emptyEventsByRole()
  }
}

function persistEventsByRole(eventsByRole: EventsByRole): void {
  if (typeof window === 'undefined') {
    return
  }
  try {
    window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(eventsByRole))
  } catch {
    // Ignore quota/storage failures and keep the UI working.
  }
}

const initialEventsByRole = loadStoredEventsByRole()

export const useConsoleStore = create<ConsoleState>((set) => ({
  selectedRole: 'all',
  connected: false,
  summary: null,
  statuses: [],
  workspace: [],
  events: flattenEventsByRole(initialEventsByRole),
  eventsByRole: initialEventsByRole,
  setSelectedRole: (selectedRole) => set({ selectedRole }),
  setConnected: (connected) => set({ connected }),
  hydrateOverview: (payload) =>
    set((state) => {
      const nextByRole = mergeRoleBuckets(state.eventsByRole, filterRelevantEvents(payload.recent_events))
      persistEventsByRole(nextByRole)
      return {
        summary: payload.summary,
        statuses: payload.roles,
        workspace: payload.workspace_files,
        events: flattenEventsByRole(nextByRole),
        eventsByRole: nextByRole,
      }
    }),
  hydrateEvents: (role, events) =>
    set((state) => {
      const relevant = filterRelevantEvents(events)
      const nextByRole = role === 'all' ? mergeRoleBuckets(state.eventsByRole, relevant) : replaceRoleBucket(state.eventsByRole, role, relevant)
      persistEventsByRole(nextByRole)
      return { events: flattenEventsByRole(nextByRole), eventsByRole: nextByRole }
    }),
  addEvent: (event) =>
    set((state) => {
      const nextByRole = mergeRoleBuckets(state.eventsByRole, filterRelevantEvents([event]))
      persistEventsByRole(nextByRole)
      return { events: flattenEventsByRole(nextByRole), eventsByRole: nextByRole }
    }),
}))

function mergeEvents(...collections: AgentEvent[][]): AgentEvent[] {
  const map = new Map<string, AgentEvent>()
  for (const collection of collections) {
    for (const event of collection) {
      map.set(event.id, event)
    }
  }
  return Array.from(map.values()).sort((left, right) => {
    const a = left.timestamp ?? ''
    const b = right.timestamp ?? ''
    return a < b ? 1 : -1
  }).slice(0, 420)
}

function mergeRoleBuckets(current: EventsByRole, incoming: AgentEvent[]): EventsByRole {
  const next = { ...current }
  for (const role of ROLE_KEYS) {
    const bucketIncoming = incoming.filter((item) => item.role === role)
    next[role] = mergeEvents(current[role], bucketIncoming)
  }
  return next
}

function replaceRoleBucket(current: EventsByRole, role: AgentRole, events: AgentEvent[]): EventsByRole {
  const next = { ...current }
  next[role] = mergeEvents(events.filter((item) => item.role === role))
  return next
}

function filterRelevantEvents(events: AgentEvent[]): AgentEvent[] {
  const tradeNames = new Set([
    'query_probability',
    'buy_yes',
    'buy_no',
    'sell_yes',
    'sell_no',
    'add_liquidity',
    'add_liquidity_yes',
    'add_liquidity_no',
    'settle',
  ])

  return events.filter((event) => {
    const payload = isObject(event.payload) ? event.payload : undefined
    const action = typeof payload?.action === 'string' ? payload.action : undefined

    if (event.role === 'proposer') {
      return event.event_type === 'action' && action === 'submit_market_review_proposal'
    }

    if (event.role === 'reviewer' || event.role === 'resolver') {
      return event.event_type === 'decision'
    }

    if (event.role === 'trader') {
      return event.event_type === 'action' && tradeNames.has(action ?? '')
    }

    return false
  })
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isAgentEventLike(value: unknown): value is AgentEvent {
  if (!isObject(value)) {
    return false
  }
  return (
    typeof value.id === 'string' &&
    typeof value.role === 'string' &&
    typeof value.agent_name === 'string' &&
    typeof value.event_type === 'string' &&
    typeof value.content === 'string'
  )
}
