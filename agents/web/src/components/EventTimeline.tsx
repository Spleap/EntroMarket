import type { AgentEvent } from '@/types/console'
import { EventCard } from '@/components/EventCard'

type EventTimelineProps = {
  events: AgentEvent[]
  eyebrow?: string
  title?: string
  emptyText?: string
  containerClassName?: string
  listClassName?: string
}

export function EventTimeline({
  events,
  eyebrow = 'Activity Stream',
  title = 'Market Interaction Feed',
  emptyText = '当前还没有可展示的 Agent 事件。',
  containerClassName = '',
  listClassName = 'max-h-[1080px]',
}: EventTimelineProps) {
  return (
    <section className={`flex min-h-0 flex-col rounded-[30px] border border-white/10 bg-slate-950/55 p-5 shadow-[0_0_40px_rgba(15,23,42,0.4)] ${containerClassName}`}>
      <div className="mb-5 flex shrink-0 items-center justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">{eyebrow}</p>
          <h2 className="mt-2 text-xl font-semibold text-white">{title}</h2>
        </div>
        <div className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-4 py-2 text-xs uppercase tracking-[0.24em] text-cyan-100">
          {events.length} events
        </div>
      </div>

      <div className={`flex flex-1 flex-col gap-4 overflow-y-auto pr-1 ${listClassName}`}>
        {events.length > 0 ? (
          events.map((event) => <EventCard key={event.id} event={event} />)
        ) : (
          <div className="rounded-[24px] border border-dashed border-white/10 bg-white/[0.02] px-5 py-10 text-center text-sm text-slate-400">
            {emptyText}
          </div>
        )}
      </div>
    </section>
  )
}
