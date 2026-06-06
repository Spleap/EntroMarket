import { Bot, FileClock, Signal, Users } from 'lucide-react'
import type { RoleSummary } from '@/types/console'

const roleLabels: Record<string, string> = {
  reviewer: '命题审核团',
  resolver: '裁决团',
  proposer: '命题发起者',
  trader: '交易员',
}

type StatusGridProps = {
  statuses: RoleSummary[]
}

export function StatusGrid({ statuses }: StatusGridProps) {
  return (
    <section className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-4">
      {statuses.map((status) => (
        <article
          key={status.role}
          className="rounded-[24px] border border-white/10 bg-slate-950/60 p-5 shadow-[0_18px_50px_rgba(15,23,42,0.28)]"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">{status.role}</p>
              <h2 className="mt-2 text-lg font-semibold text-white">{roleLabels[status.role] ?? status.role}</h2>
            </div>
            <div className={`rounded-full px-3 py-1 text-[11px] uppercase tracking-[0.24em] ${status.live ? 'bg-emerald-400/15 text-emerald-200' : 'bg-white/8 text-slate-400'}`}>
              {status.live ? 'Streaming' : 'Idle'}
            </div>
          </div>

          <div className="mt-5 grid gap-3 text-sm text-slate-300">
            <StatusRow icon={<Signal className="h-4 w-4" />} label="事件数" value={String(status.event_count)} />
            <StatusRow icon={<Users className="h-4 w-4" />} label="配置 Agent" value={String(status.configured_agent_count)} />
            <StatusRow icon={<FileClock className="h-4 w-4" />} label="最近时间" value={formatTime(status.last_timestamp)} />
            <StatusRow icon={<Bot className="h-4 w-4" />} label="最近活跃" value={status.live_agent_names.slice(0, 2).join(', ') || '暂无'} />
          </div>
        </article>
      ))}
    </section>
  )
}

type StatusRowProps = {
  icon: React.ReactNode
  label: string
  value: string
}

function StatusRow({ icon, label, value }: StatusRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl border border-white/5 bg-white/[0.03] px-3 py-2">
      <div className="flex items-center gap-2 text-slate-400">{icon}<span>{label}</span></div>
      <span className="max-w-[58%] truncate text-right font-medium text-slate-100">{value}</span>
    </div>
  )
}

function formatTime(value?: string | null): string {
  if (!value) {
    return '暂无'
  }
  return new Date(value).toLocaleTimeString('zh-CN', { hour12: false })
}
