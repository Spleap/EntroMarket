import { Activity, Bot, Orbit, Radio, Sparkles } from 'lucide-react'
import type { ConsoleSummary, RoleSummary } from '@/types/console'

function formatTime(value?: string | null): string {
  if (!value) {
    return '暂无活动'
  }
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

type TopBarProps = {
  connected: boolean
  summary: ConsoleSummary | null
  statuses: RoleSummary[]
}

export function TopBar({ connected, summary, statuses }: TopBarProps) {
  const liveCount = summary?.live_agent_total ?? statuses.filter((item) => item.live).length
  const totalAgents = summary?.configured_agent_total ?? 0
  const totalEvents = statuses.reduce((sum, item) => sum + item.event_count, 0)
  const liveAgentNames = new Set(summary?.live_agent_names ?? [])
  const agents = summary?.configured_agents ?? []

  return (
    <header className="overflow-hidden rounded-[32px] border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.18),transparent_28%),radial-gradient(circle_at_top_right,rgba(168,85,247,0.18),transparent_28%),linear-gradient(180deg,rgba(2,6,23,0.92),rgba(8,15,36,0.84))] px-6 py-6 shadow-[0_0_80px_rgba(8,145,178,0.12)] backdrop-blur-xl">
      <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
        <div className="space-y-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-xs uppercase tracking-[0.3em] text-cyan-200">
            <Radio className="h-3.5 w-3.5" />
            EntropyMarket Live Swarm
          </div>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">Autonomous Agents Trading The Market</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300 sm:text-base">
              实时展示 AI agent 在 EntropyMarket 上搜索信号、调用工具、审核命题、裁决结果与执行交易的完整痕迹。
            </p>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:min-w-[560px] xl:grid-cols-4">
          <InfoBadge
            icon={<Radio className="h-4 w-4" />}
            label="Stream"
            value={connected ? 'LIVE' : 'RECONNECTING'}
            tone={connected ? 'ok' : 'idle'}
          />
          <InfoBadge
            icon={<Bot className="h-4 w-4" />}
            label="Agents"
            value={`${totalAgents}`}
            tone="ok"
          />
          <InfoBadge
            icon={<Orbit className="h-4 w-4" />}
            label="Active Now"
            value={`${liveCount}`}
            tone="ok"
          />
          <InfoBadge
            icon={<Activity className="h-4 w-4" />}
            label="Trace Volume"
            value={`${totalEvents}`}
            tone="idle"
          />
        </div>
      </div>

      {agents.length > 0 ? (
        <div className="mt-6 flex flex-wrap gap-2">
          {agents.map((agent) => {
            const live = liveAgentNames.has(agent.agent_name)
            return (
              <div
                key={`${agent.role}:${agent.agent_name}`}
                className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs ${
                  live
                    ? 'border-cyan-300/40 bg-cyan-400/12 text-cyan-100 shadow-[0_0_20px_rgba(34,211,238,0.18)]'
                    : 'border-white/10 bg-white/5 text-slate-300'
                }`}
              >
                <span className={`h-2 w-2 rounded-full ${live ? 'bg-cyan-300 shadow-[0_0_12px_rgba(34,211,238,0.9)]' : 'bg-slate-500'}`} />
                <span>{agent.agent_name}</span>
              </div>
            )
          })}
        </div>
      ) : null}
    </header>
  )
}

type InfoBadgeProps = {
  icon: React.ReactNode
  label: string
  value: string
  tone: 'ok' | 'idle'
}

function InfoBadge({ icon, label, value, tone }: InfoBadgeProps) {
  const toneClass = tone === 'ok'
    ? 'border-emerald-400/20 bg-emerald-400/10 text-emerald-100'
    : 'border-white/10 bg-white/5 text-slate-100'

  return (
    <div className={`min-w-[140px] rounded-2xl border px-4 py-3 ${toneClass}`}>
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.24em] text-slate-300">{icon}{label}</div>
      <div className="mt-2 text-lg font-semibold tracking-wide text-white">{value}</div>
    </div>
  )
}
