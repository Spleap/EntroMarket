import { memo, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { Brain, CheckCircle2, ChevronRight, Hammer, KeyRound, MessageSquareMore, Radar, Sparkles, Wrench, XCircle } from 'lucide-react'
import type { AgentEvent } from '@/types/console'

const roleTone: Record<string, string> = {
  reviewer: 'border-emerald-400/25 bg-emerald-400/6',
  resolver: 'border-violet-400/25 bg-violet-400/6',
  proposer: 'border-amber-400/25 bg-amber-400/6',
  trader: 'border-cyan-400/25 bg-cyan-400/6',
}

const eventMeta: Record<string, { icon: React.ReactNode; label: string }> = {
  status: { icon: <Radar className="h-4 w-4" />, label: 'Status' },
  task: { icon: <Sparkles className="h-4 w-4" />, label: 'Task' },
  thought: { icon: <Brain className="h-4 w-4" />, label: 'Thought' },
  tool_call: { icon: <Wrench className="h-4 w-4" />, label: 'Tool Call' },
  tool_result: { icon: <Hammer className="h-4 w-4" />, label: 'Tool Result' },
  action: { icon: <KeyRound className="h-4 w-4" />, label: 'Action' },
  final: { icon: <CheckCircle2 className="h-4 w-4" />, label: 'Final' },
  decision: { icon: <MessageSquareMore className="h-4 w-4" />, label: 'Decision' },
  fallback: { icon: <Sparkles className="h-4 w-4" />, label: 'Fallback' },
  tool_error: { icon: <XCircle className="h-4 w-4" />, label: 'Error' },
}

type EventCardProps = {
  event: AgentEvent
}

function EventCardInner({ event }: EventCardProps) {
  const meta = eventMeta[event.event_type] ?? eventMeta.tool_result
  const tone = roleTone[event.role] ?? 'border-white/10 bg-white/[0.03]'
  const payload = isObject(event.payload) ? event.payload : undefined
  const actionName = typeof payload?.action === 'string' ? payload.action : undefined
  const toolName = typeof payload?.tool_name === 'string' ? payload.tool_name : inferToolName(event.content)
  const toolInput = isObject(payload?.tool_input) ? payload.tool_input : inferToolInput(event.content)
  const toolResult = payload?.result
  const actionPayload = isObject(payload?.payload) ? payload.payload : undefined
  const actionDetails = buildActionDetails(payload, actionPayload)
  const [showRawTrace, setShowRawTrace] = useState(false)
  const rawTraceText = useMemo(() => {
    if (!showRawTrace || !event.payload) {
      return ''
    }
    return JSON.stringify(event.payload, null, 2)
  }, [event.payload, showRawTrace])
  const isSignedMarketAction =
    ['proposer', 'trader'].includes(event.role) &&
    (
      (typeof payload?.auth_mode === 'string' && payload.auth_mode === 'eip712_signed_api') ||
      ['submit_market_review_proposal', 'buy_yes', 'buy_no', 'sell_yes', 'sell_no', 'add_liquidity', 'add_liquidity_yes', 'add_liquidity_no', 'query_probability', 'settle'].includes(actionName ?? toolName ?? '')
    )

  return (
    <article className={`rounded-[26px] border p-4 shadow-[0_0_24px_rgba(15,23,42,0.25)] ${tone}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-[0.24em] text-slate-400">
        <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/15 px-3 py-1 text-slate-100">{meta.icon}{meta.label}</span>
        <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1">{event.role}</span>
        <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1">{event.agent_name}</span>
        {isSignedMarketAction ? (
          <span className="rounded-full border border-amber-300/25 bg-amber-400/10 px-3 py-1 text-amber-100">
            <span className="inline-flex items-center gap-1">
              <KeyRound className="h-3.5 w-3.5" />
              Signed API
            </span>
          </span>
        ) : null}
        <span className="ml-auto text-slate-500">{formatTimestamp(event.timestamp)}</span>
      </div>

      <div className="mt-4 space-y-4">
        <div>
          <h3 className="text-base font-semibold text-white">{event.title || event.event_type}</h3>
          <EventContent event={event} />
        </div>

        {event.event_type === 'thought' ? (
          <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 rounded-2xl bg-white/10 p-2 text-cyan-200">
                <Brain className="h-4 w-4" />
              </div>
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Reasoning</p>
                <p className="text-sm leading-6 text-slate-200">{event.content}</p>
              </div>
            </div>
          </div>
        ) : null}

        {event.event_type === 'tool_call' && toolName ? (
          <div className="rounded-2xl border border-cyan-400/20 bg-slate-950/70 p-4">
            <div className="flex items-center gap-2 text-cyan-200">
              <ChevronRight className="h-4 w-4" />
              <span className="text-sm font-semibold">{toolName}</span>
            </div>
            {toolInput && Object.keys(toolInput).length > 0 ? (
              <StructuredGrid className="mt-3" data={toolInput} />
            ) : (
              <p className="mt-3 text-sm text-slate-400">无额外参数</p>
            )}
          </div>
        ) : null}

        {event.event_type === 'tool_result' && toolResult ? (
          <div className="rounded-2xl border border-emerald-400/20 bg-emerald-400/5 p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-emerald-200">Output Snapshot</p>
            <StructuredValue className="mt-3" value={toolResult} />
          </div>
        ) : null}

        {event.event_type === 'action' ? (
          <div className="rounded-2xl border border-amber-300/20 bg-amber-400/6 p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-amber-100">Signed Market Action</p>
            <p className="mt-3 text-sm leading-6 text-slate-100">{event.content}</p>
            {actionDetails && Object.keys(actionDetails).length > 0 ? (
              <StructuredGrid className="mt-3" data={actionDetails} />
            ) : null}
          </div>
        ) : null}

        {event.event_type === 'final' || event.event_type === 'decision' ? (
          <div className="rounded-2xl border border-violet-400/20 bg-violet-400/8 p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-violet-200">Committed Action</p>
            <p className="mt-3 text-sm leading-6 text-slate-100">{event.content}</p>
          </div>
        ) : null}

        {event.event_type === 'status' ? (
          <div className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-slate-300">
            {event.content}
          </div>
        ) : null}

        {event.event_type === 'tool_error' || event.event_type === 'fallback' ? (
          <div className="rounded-2xl border border-rose-400/20 bg-rose-400/8 p-4 text-sm leading-6 text-rose-100">
            {event.content}
          </div>
        ) : null}
      </div>

      {event.payload ? (
        <details
          className="mt-4 rounded-2xl border border-white/10 bg-slate-950/75 p-3 text-xs text-slate-300"
          onToggle={(detailsEvent) => setShowRawTrace(detailsEvent.currentTarget.open)}
        >
          <summary className="cursor-pointer list-none text-[11px] uppercase tracking-[0.26em] text-slate-400">Raw Trace</summary>
          {showRawTrace ? (
            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-all text-[11px] leading-5 text-cyan-100">{rawTraceText}</pre>
          ) : null}
        </details>
      ) : null}
    </article>
  )
}

export const EventCard = memo(EventCardInner)

function formatTimestamp(value?: string) {
  if (!value) {
    return '未知时间'
  }
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function EventContent({ event }: { event: AgentEvent }) {
  const useRichMarkdown = event.event_type === 'thought' || event.event_type === 'tool_call' || event.event_type === 'tool_result'

  if (!useRichMarkdown) {
    return <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-100">{event.content}</p>
  }

  return (
    <div className="prose prose-invert mt-3 max-w-none prose-p:my-2 prose-pre:rounded-2xl prose-pre:border prose-pre:border-white/10 prose-pre:bg-slate-950/90 prose-code:text-cyan-200">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
        {event.content}
      </ReactMarkdown>
    </div>
  )
}

function inferToolName(content: string) {
  const match = content.match(/^([a-zA-Z0-9_]+)\(/)
  return match?.[1]
}

function inferToolInput(content: string) {
  const match = content.match(/^[a-zA-Z0-9_]+\(([\s\S]*)\)$/)
  if (!match?.[1]) {
    return undefined
  }
  try {
    const parsed = JSON.parse(match[1])
    return isObject(parsed) ? parsed : undefined
  } catch {
    return undefined
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function buildActionDetails(
  payload?: Record<string, unknown>,
  actionPayload?: Record<string, unknown>,
): Record<string, unknown> | undefined {
  if (!payload) {
    return undefined
  }

  const details: Record<string, unknown> = {}
  const actionName = typeof payload.action === 'string' ? payload.action : undefined
  const marketTitle = typeof payload.market_title === 'string' ? payload.market_title : undefined
  const apiPath = typeof payload.api_path === 'string' ? payload.api_path : undefined

  if (actionName) {
    details.action = actionName
  }
  if (marketTitle) {
    details.market = marketTitle
  }
  if (apiPath) {
    details.route = apiPath
  }

  if (actionName === 'query_probability') {
    if (typeof actionPayload?.probability_yes === 'string' || typeof actionPayload?.probability_yes === 'number') {
      details.probability_yes = formatProbabilityPercent(actionPayload.probability_yes)
    }
    if (actionPayload?.entropy_fee_charged != null) {
      details.entropy_fee = actionPayload.entropy_fee_charged
    }
    return details
  }

  const trade = isObject(actionPayload?.trade) ? actionPayload.trade : undefined
  if (trade) {
    if (trade.side != null) {
      details.side = trade.side
    }
    if (trade.share_delta != null) {
      details.share_delta = trade.share_delta
    }
    if (trade.total_amount != null) {
      details.total_amount = trade.total_amount
    }
    if (trade.probability_yes_before != null) {
      details.probability_before = formatProbabilityPercent(trade.probability_yes_before)
    }
    if (trade.probability_yes_after != null) {
      details.probability_after = formatProbabilityPercent(trade.probability_yes_after)
    }
  }

  return details
}

function formatProbabilityPercent(value: unknown): string {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) {
    return String(value)
  }
  return `${(numeric * 100).toFixed(2)}%`
}

function StructuredGrid({ data, className = '' }: { data: Record<string, unknown>; className?: string }) {
  const entries = Object.entries(data).slice(0, 6)
  return (
    <div className={`grid gap-3 sm:grid-cols-2 ${className}`}>
      {entries.map(([key, value]) => (
        <div key={key} className="rounded-2xl border border-white/10 bg-black/20 p-3">
          <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">{key}</p>
          <p className="mt-2 text-sm text-slate-100">{formatValue(value)}</p>
        </div>
      ))}
    </div>
  )
}

function StructuredValue({ value, className = '' }: { value: unknown; className?: string }) {
  if (Array.isArray(value)) {
    return (
      <div className={className}>
        <div className="rounded-2xl border border-white/10 bg-black/20 p-3 text-sm text-slate-200">
          返回 {value.length} 项结果
        </div>
      </div>
    )
  }
  if (isObject(value)) {
    return <StructuredGrid data={value} className={className} />
  }
  return <p className={`text-sm text-slate-100 ${className}`}>{formatValue(value)}</p>
}

function formatValue(value: unknown) {
  if (value == null) {
    return 'null'
  }
  if (typeof value === 'string') {
    return value.length > 160 ? `${value.slice(0, 157)}...` : value
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  if (Array.isArray(value)) {
    return `${value.length} item(s)`
  }
  if (isObject(value)) {
    return Object.keys(value).join(', ') || '{}'
  }
  return String(value)
}
