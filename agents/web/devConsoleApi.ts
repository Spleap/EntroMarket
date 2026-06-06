import fs from 'node:fs'
import path from 'node:path'
import type { IncomingMessage, ServerResponse } from 'node:http'
import type { Connect, Plugin } from 'vite'

type Role = 'reviewer' | 'resolver' | 'proposer' | 'trader'

const agentDir = path.resolve(__dirname, '..')
const roleFiles: Record<Role, string> = {
  reviewer: path.join(agentDir, 'logs', 'reviewer_activity.jsonl'),
  resolver: path.join(agentDir, 'logs', 'resolver_activity.jsonl'),
  proposer: path.join(agentDir, 'logs', 'proposer_activity.jsonl'),
  trader: path.join(agentDir, 'logs', 'trader_activity.jsonl'),
}
const roleWalletSpecs: Record<
  Role,
  { walletsFile: string; walletStart: string; walletCount: string }
> = {
  reviewer: {
    walletsFile: 'REVIEWER_WALLETS_FILE',
    walletStart: 'REVIEWER_WALLET_START',
    walletCount: 'REVIEWER_WALLET_COUNT',
  },
  resolver: {
    walletsFile: 'REVIEWER_WALLETS_FILE',
    walletStart: 'RESOLVER_WALLET_START',
    walletCount: 'RESOLVER_WALLET_COUNT',
  },
  proposer: {
    walletsFile: 'PARTICIPANT_WALLETS_FILE',
    walletStart: 'PROPOSER_WALLET_START',
    walletCount: 'PROPOSER_WALLET_COUNT',
  },
  trader: {
    walletsFile: 'PARTICIPANT_WALLETS_FILE',
    walletStart: 'TRADER_WALLET_START',
    walletCount: 'TRADER_WALLET_COUNT',
  },
}

export function devConsoleApiPlugin(): Plugin {
  return {
    name: 'dev-console-api',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const requestUrl = new URL(req.url ?? '/', 'http://localhost')
        if (!requestUrl.pathname.startsWith('/api/')) {
          next()
          return
        }
        void handleApi(req, res, requestUrl, next)
      })
    },
  }
}

async function handleApi(
  req: IncomingMessage,
  res: ServerResponse<IncomingMessage>,
  requestUrl: URL,
  next: Connect.NextFunction,
) {
  if (requestUrl.pathname === '/api/overview') {
    json(res, buildOverview())
    return
  }
  if (requestUrl.pathname === '/api/events') {
    const role = requestUrl.searchParams.get('role') ?? 'all'
    const limit = Number(requestUrl.searchParams.get('limit') ?? '120')
    const events = loadRoles(role).slice(0, limit)
    json(res, { events })
    return
  }
  if (requestUrl.pathname === '/api/workspace') {
    const roots = ['logs', 'state']
      .map((item) => path.join(agentDir, item))
      .filter((item) => fs.existsSync(item))
    const items = roots.flatMap((root) =>
      fs.readdirSync(root).map((name) => {
        const fullPath = path.join(root, name)
        const stat = fs.statSync(fullPath)
        return {
          name,
          path: fullPath,
          kind: stat.isDirectory() ? 'dir' : 'file',
          size: stat.isFile() ? stat.size : null,
        }
      }),
    )
    json(res, { items })
    return
  }
  if (requestUrl.pathname === '/api/stream') {
    streamEvents(res, requestUrl.searchParams.get('role') ?? 'all')
    return
  }
  next()
}

function buildOverview() {
  const configuredAgentsByRole = buildConfiguredAgentsByRole()
  const roles = (Object.keys(roleFiles) as Role[]).map((role) => {
    const events = loadRole(role)
    const configuredAgents = configuredAgentsByRole[role] ?? []
    const configuredAgentNames = configuredAgents.map((item) => item.agent_name)
    const observedAgentNames = [...new Set(events.map((item) => item.agent_name))]
    const liveAgentNames = [
      ...new Set(
        events
          .filter((item) => isRecentTimestamp(item.timestamp))
          .map((item) => item.agent_name),
      ),
    ]
    const lastTimestamp = events[0]?.timestamp ?? null
    const live =
      typeof lastTimestamp === 'string' && Date.now() - new Date(lastTimestamp).getTime() <= 180_000
    return {
      role,
      file_path: roleFiles[role],
      exists: fs.existsSync(roleFiles[role]),
      event_count: events.length,
      last_timestamp: lastTimestamp,
      live,
      configured_agent_count: configuredAgents.length,
      configured_agent_names: configuredAgentNames,
      observed_agent_count: observedAgentNames.length,
      observed_agent_names: observedAgentNames,
      live_agent_count: liveAgentNames.length,
      live_agent_names: liveAgentNames,
    }
  })

  const recentEvents = loadRoles('all').slice(0, 40)
  const workspaceFiles = fs
    .readdirSync(agentDir)
    .filter((name) => !['__pycache__', '.env', 'web'].includes(name))
    .map((name) => {
      const fullPath = path.join(agentDir, name)
      const stat = fs.statSync(fullPath)
      return {
        name,
        path: fullPath,
        kind: stat.isDirectory() ? 'dir' : 'file',
      }
    })

  const configuredAgents = Object.entries(configuredAgentsByRole).flatMap(([role, items]) =>
    items.map((item) => ({ role, ...item })),
  )
  const observedAgentNames = [...new Set(recentEvents.map((item) => item.agent_name))]
  const liveAgentNames = [
    ...new Set(recentEvents.filter((item) => isRecentTimestamp(item.timestamp)).map((item) => item.agent_name)),
  ]

  return {
    summary: {
      configured_agent_total: configuredAgents.length,
      configured_agents: configuredAgents,
      observed_agent_total: observedAgentNames.length,
      observed_agent_names: observedAgentNames,
      live_agent_total: liveAgentNames.length,
      live_agent_names: liveAgentNames,
      latest_timestamp: recentEvents[0]?.timestamp ?? null,
    },
    roles,
    recent_events: recentEvents,
    workspace_files: workspaceFiles,
  }
}

function loadRoles(role: string) {
  const roles = role === 'all' ? (Object.keys(roleFiles) as Role[]) : [role as Role]
  return roles
    .filter((item): item is Role => item in roleFiles)
    .flatMap((item) => loadRole(item))
    .sort((left, right) => String(right.timestamp ?? '').localeCompare(String(left.timestamp ?? '')))
}

function loadRole(role: Role) {
  const filePath = roleFiles[role]
  if (!fs.existsSync(filePath)) {
    return []
  }
  const content = fs.readFileSync(filePath, 'utf-8')
  return content
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => {
      try {
        return normalizeEvent(JSON.parse(line), role)
      } catch {
        return null
      }
    })
    .filter(Boolean) as ReturnType<typeof normalizeEvent>[]
}

function buildConfiguredAgentsByRole() {
  return (Object.keys(roleWalletSpecs) as Role[]).reduce<Record<Role, Array<{ agent_name: string; address: string }>>>(
    (output, role) => {
      output[role] = loadWalletSlice(role)
      return output
    },
    {
      reviewer: [],
      resolver: [],
      proposer: [],
      trader: [],
    },
  )
}

function loadWalletSlice(role: Role) {
  const spec = roleWalletSpecs[role]
  const walletsFile = process.env[spec.walletsFile]
  if (!walletsFile || !fs.existsSync(walletsFile)) {
    return []
  }
  try {
    const raw = JSON.parse(fs.readFileSync(walletsFile, 'utf-8')) as Array<Record<string, unknown>>
    const start = Math.max(Number(process.env[spec.walletStart] ?? '1') - 1, 0)
    const count = Math.max(Number(process.env[spec.walletCount] ?? '5'), 0)
    return raw.slice(start, start + count).map((item) => ({
      agent_name: String(item.agent_name ?? ''),
      address: String(item.address ?? '').toLowerCase(),
    }))
  } catch {
    return []
  }
}

function normalizeEvent(raw: Record<string, unknown>, role: Role) {
  if (typeof raw.event_type === 'string') {
    return {
      id: buildEventId(raw, role),
      timestamp: raw.timestamp,
      role: (raw.role as string | undefined) ?? role,
      agent_name: (raw.agent_name as string | undefined) ?? role,
      event_type: raw.event_type,
      content: (raw.content as string | undefined) ?? '',
      payload: raw.payload,
      title: raw.event_type,
    }
  }

  const agentName = (raw.agent_name as string | undefined) ?? role
  const title =
    (raw.proposal_title as string | undefined) ??
    (raw.market_title as string | undefined) ??
    (raw.query as string | undefined) ??
    (raw.action as string | undefined) ??
    role

  if (role === 'reviewer' && typeof raw.vote === 'string') {
    return {
      id: buildEventId(raw, role),
      timestamp: raw.timestamp,
      role,
      agent_name: agentName,
      event_type: 'decision',
      content: `${agentName} 对命题投了 ${raw.vote}。${(raw.summary as string | undefined) ?? ''}`.trim(),
      payload: raw,
      title,
    }
  }

  if (role === 'resolver' && raw.action === 'create_resolution_proposal') {
    return {
      id: buildEventId(raw, role),
      timestamp: raw.timestamp,
      role,
      agent_name: agentName,
      event_type: 'tool_result',
      content: `${agentName} 创建了 resolution proposal，outcome=${String(raw.proposed_outcome ?? '')}`,
      payload: raw,
      title,
    }
  }

  if (role === 'resolver' && typeof raw.vote === 'string') {
    return {
      id: buildEventId(raw, role),
      timestamp: raw.timestamp,
      role,
      agent_name: agentName,
      event_type: 'decision',
      content: `${agentName} 对结算提案投了 ${raw.vote}。${(raw.rationale as string | undefined) ?? ''}`.trim(),
      payload: raw,
      title,
    }
  }

  if (role === 'proposer' && raw.action === 'submit_market_review_proposal') {
    return {
      id: buildEventId(raw, role),
      timestamp: raw.timestamp,
      role,
      agent_name: agentName,
      event_type: 'final',
      content: `从 tweet ${String(raw.tweet_id ?? '')} 提交了命题：${String(raw.proposal_title ?? '')}`,
      payload: raw,
      title,
    }
  }

  if (role === 'proposer' && raw.action === 'skip_candidate') {
    return {
      id: buildEventId(raw, role),
      timestamp: raw.timestamp,
      role,
      agent_name: agentName,
      event_type: 'thought',
      content: `跳过 tweet ${String(raw.tweet_id ?? '')}，query=${String(raw.query ?? '')}`,
      payload: raw,
      title,
    }
  }

  return {
    id: buildEventId(raw, role),
    timestamp: raw.timestamp,
    role,
    agent_name: agentName,
    event_type: 'tool_result',
    content: `${agentName} 执行了 ${String(raw.action ?? raw.vote ?? 'event')}`,
    payload: raw,
    title,
  }
}

function buildEventId(raw: Record<string, unknown>, role: Role) {
  return [
    role,
    raw.timestamp ?? '',
    raw.agent_name ?? '',
    raw.proposal_id ?? raw.market_id ?? raw.tweet_id ?? raw.action ?? raw.vote ?? 'event',
  ].join(':')
}

function isRecentTimestamp(value: unknown) {
  return typeof value === 'string' && Date.now() - new Date(value).getTime() <= 180_000
}

function json(res: ServerResponse<IncomingMessage>, payload: unknown) {
  const body = JSON.stringify(payload)
  res.statusCode = 200
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.end(body)
}

function streamEvents(res: ServerResponse<IncomingMessage>, role: string) {
  res.statusCode = 200
  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache')
  res.setHeader('Connection', 'keep-alive')

  const seen = new Set(loadRoles(role).map((item) => item.id))
  const timer = setInterval(() => {
    const nextItems = loadRoles(role).filter((item) => !seen.has(item.id)).reverse()
    for (const item of nextItems) {
      seen.add(item.id)
      res.write(`data: ${JSON.stringify(item)}\n\n`)
    }
    res.write(': ping\n\n')
  }, 1000)

  res.on('close', () => {
    clearInterval(timer)
    res.end()
  })
}
