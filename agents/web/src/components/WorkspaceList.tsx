import { FileCode2, FolderKanban } from 'lucide-react'
import type { WorkspaceItem } from '@/types/console'

type WorkspaceListProps = {
  items: WorkspaceItem[]
}

export function WorkspaceList({ items }: WorkspaceListProps) {
  return (
    <section className="rounded-[28px] border border-white/10 bg-slate-950/60 p-5">
      <div className="mb-5">
        <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Workspace</p>
        <h2 className="mt-2 text-xl font-semibold text-white">本地目录快照</h2>
      </div>

      <div className="grid max-h-[360px] gap-3 overflow-y-auto pr-1">
        {items.map((item) => (
          <div key={item.path} className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3">
            <div className="flex items-center gap-3 text-sm text-white">
              {item.kind === 'dir' ? <FolderKanban className="h-4 w-4 text-amber-300" /> : <FileCode2 className="h-4 w-4 text-cyan-300" />}
              <span className="truncate">{item.name}</span>
            </div>
            <p className="mt-2 truncate text-xs text-slate-400">{item.path}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
