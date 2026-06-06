# Entropy Zero Agent Runtime

This directory contains the role-based multi-agent runtime for the Entropy Zero demo.

## What It Does

- Reviewer cluster:
  - Watches `GET /governance/market-proposals`
  - Evaluates whether a proposal is clear, resolvable, future-dated, and policy-safe
  - Signs review votes and can finalize approved proposals
- Resolver cluster:
  - Watches `GET /amm/markets?status=closed`
  - Creates `resolution proposals` when a closed market still needs settlement review
  - Uses `xAPI` plus optional `DeepSeek` reasoning to infer the defensible outcome
  - Signs `veto / no_veto` votes and can finalize the resolution review
- Proposer cluster:
  - Watches X/Twitter via `xAPI`
  - Runs as ordinary market participants, not governance NPCs
  - Uses multiple participant wallets to submit market review proposals
  - Filters high-signal tweets
  - Uses `DeepSeek` to convert eligible tweets into objective market review proposals
  - Signs and submits `POST /governance/market-proposals`
- Trader cluster:
  - Runs as ordinary market participants, not governance NPCs
  - Searches open markets and inspects account state
  - Can query paid probability, search outside evidence, and decide whether to trade
  - Uses the same chat-style tool-calling runtime as the other roles

## Current Scope

This folder currently implements:

- reviewer agents
- resolver agents
- proposer agents
- trader agents

## Files

- `main.py`: CLI entrypoint
- `config.py`: environment loading and runtime configuration
- `models.py`: shared dataclasses
- `entromarket_client.py`: signed API client and bootstrap helpers
- `reviewer_policy.py`: review rules and decision logic
- `reviewer_agent.py`: reviewer worker orchestration
- `resolver_policy.py`: resolution assessment logic
- `resolver_agent.py`: resolver worker orchestration
- `proposer_policy.py`: tweet filtering and proposal drafting logic
- `proposer_agent.py`: proposer participant cluster
- `trader_agent.py`: trader worker orchestration
- `chat_runtime.py`: shared chat-style tool-calling runtime and structured trace logger
- `console_server.py`: local dashboard API and optional static file host for the web console
- `xapi_client.py`: `xapi-to` adapter
- `deepseek_client.py`: optional LLM reasoning adapter
- `web/`: React-based live dashboard for agent traces

## Setup

1. Create a virtual environment
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill values
4. Run one reviewer cycle:

```bash
python main.py reviewer-run-once
```

5. Run reviewer as a watcher:

```bash
python main.py reviewer-watch
```

6. Run one resolver cycle:

```bash
python main.py resolver-run-once
```

7. Run resolver as a watcher:

```bash
python main.py resolver-watch
```

8. Run one proposer cycle:

```bash
python main.py proposer-run-once
```

9. Run proposer as a watcher:

```bash
python main.py proposer-watch
```

10. Run one trader cycle:

```bash
python main.py trader-run-once
```

11. Run trader as a watcher:

```bash
python main.py trader-watch
```

12. Run the live dashboard API:

```bash
python console_server.py
```

13. Start the web console in development:

```bash
cd web
npm install
npm run dev
```

14. Build the web console for static hosting:

```bash
cd web
npm run build
```

15. Fund participant wallets for proposer/trader swarm:

```bash
python fund_participant_wallets.py
```

16. Build the frontend for static hosting and serve it via `console_server.py` or your own web server.

Recommended demo topology:

- Governance layer: `5` reviewer agents voting on pending market review proposals
- Governance layer: `5` resolver agents watching matured markets and handling resolution review
- Market participant layer: `5` proposer agents watching X and submitting proposals
- Market participant layer: `5` trader agents watching markets and deciding whether to trade

## Wallet Source

The default setup expects governance wallets to be loaded from a local wallet file, for example:

- `../sepolia_agent_wallets.json`

The default setup expects participant wallets to be loaded from a local wallet file, for example:

- `../sepolia_agent_wallets.json`

The default wallet split is:

- wallets `1-5`: reviewer agents
- wallets `6-10`: resolver agents
- wallets `11-15`: proposer agents
- wallets `16-20`: trader agents

## Notes

- Reviewer agents use the wallet address itself as `account_id`
- Reviewer agents register with `erc8004_agent_id` derived from `REVIEWER_AGENT_ID_PREFIX`
- Resolver agents register with `erc8004_agent_id` derived from `RESOLVER_AGENT_ID_PREFIX`
- Proposer and trader wallets are ordinary participant accounts and do not need governance stake
- If backend state is empty after restart, the agent can re-deposit and re-stake automatically
- If a resolver wallet lacks a tiny amount of `ENTROPY` due to earlier demo spending, the configured funder key can top it up before deposit
- Proposer cluster keeps a shared local state file so the same tweet is not turned into repeated market proposals
- Proposer polling cadence is configurable via `PROPOSER_POLL_INTERVAL_SECONDS`
- Proposer can top up its backend USDNB ledger from on-chain USDNB before submitting a market proposal
- Trader writes structured `task / thought / tool_call / tool_result / final` events into `TRADER_LOG_PATH`
- Reviewer, resolver, and proposer now also emit structured chat-style trace events into their existing log files
- `console_server.py` reads these JSONL traces and can also serve `web/dist` after frontend build
- `docker-compose.yml` runs `reviewer`, `resolver`, `proposer`, `trader`, and `console` as one Docker stack
- The Docker image includes `nodejs`/`npm` because `xapi_client.py` shells out to `npx` at runtime
- `xAPI` search is optional; if `XAPI_KEY` is missing, the policy still runs with deterministic local checks
- `DeepSeek` is optional; without it, resolver falls back to deterministic price-based or conservative veto logic

## Public Repo Notes

- Copy `.env.example` to `.env` before running the runtime locally
- Generated files under `logs/`, `state/`, and `web/dist/` are intentionally excluded from version control
- This public repository does not include live VPS deployment credentials, private wallet files, or runtime artifacts
