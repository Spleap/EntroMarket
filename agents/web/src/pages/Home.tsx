import { useMemo } from 'react'
import { EventTimeline } from '@/components/EventTimeline'
import { TopBar } from '@/components/TopBar'
import { useDashboardStream } from '@/hooks/useDashboardStream'
import { useConsoleStore } from '@/store/useConsoleStore'
import type { AgentEvent } from '@/types/console'

export default function Home() {
  const summary = useConsoleStore((state) => state.summary)
  const statuses = useConsoleStore((state) => state.statuses)
  const eventsByRole = useConsoleStore((state) => state.eventsByRole)
  const connected = useConsoleStore((state) => state.connected)

  useDashboardStream('all')

  const groupedEvents = useMemo(() => {
    return {
      proposer: eventsByRole.proposer.filter(isProposalSubmissionEvent).slice(0, 24),
      reviewer: eventsByRole.reviewer.filter((item) => item.event_type === 'decision').slice(0, 24),
      resolver: eventsByRole.resolver.filter((item) => item.event_type === 'decision').slice(0, 24),
      probability: eventsByRole.trader.filter(isProbabilityEvent).slice(0, 24),
      trade: eventsByRole.trader.filter(isTradeEvent).slice(0, 30),
    }
  }, [eventsByRole])

  return (
    <main className="min-h-screen bg-[#050816] px-4 py-6 text-white sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-[1680px] flex-col gap-6">
        <TopBar connected={connected} summary={summary} statuses={statuses} />

        <section className="grid gap-6 md:grid-cols-2 xl:grid-cols-3 items-start">
          <EventTimeline
            events={groupedEvents.proposer}
            eyebrow="Proposal Flow"
            title="Agent 发起命题"
            emptyText="暂无新的命题发起行为。"
            containerClassName="h-[500px] !border-amber-400/20"
          />
          <EventTimeline
            events={groupedEvents.reviewer}
            eyebrow="Review Votes"
            title="审核 Agent 投票"
            emptyText="暂无新的审核投票。"
            containerClassName="h-[500px] !border-emerald-400/20"
          />
          <EventTimeline
            events={groupedEvents.resolver}
            eyebrow="Resolution Votes"
            title="结算 Agent 投票"
            emptyText="暂无新的结算投票。"
            containerClassName="h-[500px] !border-violet-400/20"
          />
          <EventTimeline
            events={groupedEvents.probability}
            eyebrow="Probability Query"
            title="Agent 查看概率"
            emptyText="暂无新的概率查询行为。"
            containerClassName="h-[600px] xl:col-span-1 !border-cyan-400/20"
          />
          <EventTimeline
            events={groupedEvents.trade}
            eyebrow="Trading Flow"
            title="Agent 交易"
            emptyText="暂无新的交易行为。"
            containerClassName="h-[600px] md:col-span-2 xl:col-span-2 !border-blue-400/20"
          />
        </section>
      </div>
    </main>
  )
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function getToolName(event: AgentEvent): string | undefined {
  const payload = isObject(event.payload) ? event.payload : undefined
  const direct = payload?.tool_name
  return typeof direct === 'string' ? direct : undefined
}

function getActionName(event: AgentEvent): string | undefined {
  const payload = isObject(event.payload) ? event.payload : undefined
  const direct = payload?.action
  return typeof direct === 'string' ? direct : undefined
}

function isProposalSubmissionEvent(event: AgentEvent): boolean {
  return getActionName(event) === 'submit_market_review_proposal'
}

function isProbabilityEvent(event: AgentEvent): boolean {
  return getActionName(event) === 'query_probability' || getToolName(event) === 'query_probability'
}

function isTradeEvent(event: AgentEvent): boolean {
  const toolName = getToolName(event)
  const actionName = getActionName(event)
  const tradeNames = new Set([
    'buy_yes',
    'buy_no',
    'sell_yes',
    'sell_no',
    'add_liquidity',
    'add_liquidity_yes',
    'add_liquidity_no',
    'settle',
  ])
  return tradeNames.has(toolName ?? '') || tradeNames.has(actionName ?? '')
}
