export type AgentRole = 'reviewer' | 'resolver' | 'proposer' | 'trader'

export type EventType =
  | 'task'
  | 'thought'
  | 'tool_call'
  | 'tool_result'
  | 'action'
  | 'final'
  | 'decision'
  | 'fallback'
  | 'tool_error'
  | 'status'

export type AgentEvent = {
  id: string
  timestamp?: string
  role: AgentRole
  agent_name: string
  event_type: EventType | string
  content: string
  payload?: unknown
  title?: string
}

export type RoleSummary = {
  role: AgentRole
  file_path: string
  exists: boolean
  event_count: number
  last_timestamp?: string | null
  live: boolean
  configured_agent_count: number
  configured_agent_names: string[]
  observed_agent_count: number
  observed_agent_names: string[]
  live_agent_count: number
  live_agent_names: string[]
}

export type ConfiguredAgent = {
  role: AgentRole
  agent_name: string
  address: string
}

export type ConsoleSummary = {
  configured_agent_total: number
  configured_agents: ConfiguredAgent[]
  observed_agent_total: number
  observed_agent_names: string[]
  live_agent_total: number
  live_agent_names: string[]
  latest_timestamp?: string | null
}

export type WorkspaceItem = {
  name: string
  path: string
  kind: 'file' | 'dir'
  size?: number | null
}

export type OverviewResponse = {
  summary: ConsoleSummary
  roles: RoleSummary[]
  recent_events: AgentEvent[]
  workspace_files: WorkspaceItem[]
}

export type EventsResponse = {
  events: AgentEvent[]
}

export type HistoryResponse = {
  events: AgentEvent[]
  offset: number
  limit: number
  total: number
  has_more: boolean
  next_offset?: number | null
  archive_path: string
}
