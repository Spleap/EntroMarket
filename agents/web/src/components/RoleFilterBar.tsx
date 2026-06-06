import type { AgentRole } from '@/types/console'

const roles: Array<{ key: AgentRole | 'all'; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'reviewer', label: 'Reviewer' },
  { key: 'resolver', label: 'Resolver' },
  { key: 'proposer', label: 'Proposer' },
  { key: 'trader', label: 'Trader' },
]

type RoleFilterBarProps = {
  selectedRole: AgentRole | 'all'
  onSelect: (role: AgentRole | 'all') => void
}

export function RoleFilterBar({ selectedRole, onSelect }: RoleFilterBarProps) {
  return (
    <div className="flex flex-wrap gap-3">
      {roles.map((role) => {
        const active = role.key === selectedRole
        return (
          <button
            key={role.key}
            type="button"
            onClick={() => onSelect(role.key)}
            className={[
              'rounded-full border px-4 py-2 text-xs uppercase tracking-[0.28em] transition',
              active
                ? 'border-cyan-300/40 bg-cyan-300/15 text-cyan-100 shadow-[0_0_28px_rgba(34,211,238,0.18)]'
                : 'border-white/10 bg-white/5 text-slate-300 hover:border-cyan-300/20 hover:bg-cyan-300/10 hover:text-white',
            ].join(' ')}
          >
            {role.label}
          </button>
        )
      })}
    </div>
  )
}
