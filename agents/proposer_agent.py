from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from threading import Lock
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from chat_runtime import AgentTraceLogger, ChatStyleToolAgent, RuntimeTool
from config import ReviewerConfig
from deepseek_client import DeepSeekClient
from entromarket_client import EntroMarketClient
from models import AgentWallet
from proposer_policy import ProposerPolicy, TweetCandidate
from xapi_client import XApiClient


class ProposerCluster:
    def __init__(
        self,
        config: ReviewerConfig,
        client: EntroMarketClient,
        policy: ProposerPolicy,
        xapi_client: XApiClient,
        deepseek_client: DeepSeekClient,
        wallets: list[AgentWallet],
    ) -> None:
        self.config = config
        self.client = client
        self.policy = policy
        self.xapi_client = xapi_client
        self.deepseek_client = deepseek_client
        self.wallets = wallets
        self._state_lock = Lock()
        self.config.proposer_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.proposer_log_path.parent.mkdir(parents=True, exist_ok=True)

    def bootstrap(self) -> None:
        return

    def run_once(self) -> None:
        if not self.wallets:
            raise RuntimeError("No proposer participant wallets found. Configure PARTICIPANT_WALLETS_FILE and PROPOSER_WALLET_START/COUNT.")

        state = self._load_state()
        candidates: list[TweetCandidate] = []
        for query in self.config.proposer_search_queries:
            payload = self.xapi_client.twitter_search(query)
            query_candidates = self.policy.extract_candidates(query, payload)
            for candidate in query_candidates:
                if candidate.tweet_id in state["seen_tweet_ids"]:
                    continue
                candidates.append(candidate)

        candidates.sort(
            key=lambda item: (item.followers_count, item.favorite_count + item.reply_count + item.retweet_count, item.view_count),
            reverse=True,
        )
        candidates = candidates[: self.config.proposer_max_candidates_per_cycle]
        print(f"[proposer] candidate tweets: {len(candidates)}", flush=True)
        if not candidates:
            for wallet in self.wallets:
                self._emit_status(wallet, "监听外部信号中，当前没有值得发起的新命题。", {"candidate_count": 0})
            return

        assignments: list[tuple[AgentWallet, TweetCandidate]] = []
        for index, candidate in enumerate(candidates):
            wallet = self.wallets[index % len(self.wallets)]
            self._mark_seen_candidate(state, candidate.tweet_id)
            assignments.append((wallet, candidate))

        for wallet in self.wallets:
            assigned = [candidate.tweet_id for current_wallet, candidate in assignments if current_wallet.agent_name == wallet.agent_name]
            if assigned:
                self._emit_status(wallet, "正在分析新信号并准备命题草案。", {"tweet_ids": assigned})
            else:
                self._emit_status(wallet, "待命中，等待下一批信号。", {"candidate_count": len(candidates)})

        with ThreadPoolExecutor(max_workers=len(assignments)) as executor:
            futures = [
                executor.submit(self._run_chat_proposer, wallet=wallet, candidate=candidate, state=state)
                for wallet, candidate in assignments
            ]
            for future in as_completed(futures):
                future.result()

        self._save_state(state)

    def watch_forever(self) -> None:
        while True:
            self.run_once()
            self._sleep_with_heartbeat(self.config.proposer_poll_interval_seconds)

    def _load_state(self) -> dict:
        if not self.config.proposer_state_path.exists():
            return {"seen_tweet_ids": [], "submitted_tweet_ids": [], "submitted_proposal_ids": []}
        return json.loads(self.config.proposer_state_path.read_text(encoding="utf-8"))

    def _save_state(self, state: dict) -> None:
        self.config.proposer_state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _append_log(self, payload: dict) -> None:
        with self.config.proposer_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def _emit_status(self, wallet: AgentWallet, content: str, payload: dict | None = None) -> None:
        AgentTraceLogger(role="proposer", agent_name=wallet.agent_name, log_path=self.config.proposer_log_path).emit(
            "status",
            content,
            payload,
        )

    def _mark_seen_candidate(self, state: dict, tweet_id: str) -> None:
        with self._state_lock:
            state["seen_tweet_ids"].append(tweet_id)
            self._save_state(state)

    def _sleep_with_heartbeat(self, total_seconds: int) -> None:
        remaining = max(total_seconds, 0)
        while remaining > 0:
            chunk = min(15, remaining)
            time.sleep(chunk)
            remaining -= chunk
            for wallet in self.wallets:
                self._emit_status(wallet, "在线搜索中，持续监听新的外部信号。", {"next_cycle_in_seconds": remaining})

    def _run_chat_proposer(self, wallet: AgentWallet, candidate: TweetCandidate, state: dict) -> None:
        draft = None
        proposal = None
        submitted = False
        logger = AgentTraceLogger(role="proposer", agent_name=wallet.agent_name, log_path=self.config.proposer_log_path)
        agent = ChatStyleToolAgent(
            role="proposer",
            agent_name=wallet.agent_name,
            deepseek_client=self.deepseek_client,
            logger=logger,
        )

        def build_draft(_: dict) -> dict:
            nonlocal draft
            draft = self.policy.build_proposal(candidate)
            if draft is None:
                return {"should_submit": False, "reason": "No viable draft generated."}
            return asdict(draft)

        def ensure_balance(_: dict) -> dict:
            if draft is None:
                raise ValueError("draft is required before funding balance")
            seed_total = Decimal(draft.yes_liquidity) + Decimal(draft.no_liquidity)
            result = self.client.ensure_usdnb_ledger_balance(wallet.private_key, seed_total)
            return {"required_amount": str(seed_total), "account": result}

        def submit_proposal(_: dict) -> dict:
            nonlocal proposal, submitted
            if draft is None:
                raise ValueError("draft is required before submit")
            proposal = self.client.create_market_review_proposal(
                wallet.private_key,
                title=draft.title,
                description=draft.description,
                category=draft.category,
                tags=draft.tags,
                trading_close_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=draft.trading_close_minutes)
                ).isoformat(),
                yes_liquidity=draft.yes_liquidity,
                no_liquidity=draft.no_liquidity,
            )
            submitted = True
            with self._state_lock:
                state["submitted_tweet_ids"].append(candidate.tweet_id)
                state["submitted_proposal_ids"].append(proposal["proposal_id"])
                self._save_state(state)
            self._append_log(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": "submit_market_review_proposal",
                    "auth_mode": "eip712_signed_api",
                    "api_path": "/governance/market-proposals",
                    "agent_name": wallet.agent_name,
                    "account_id": wallet.address.lower(),
                    "tweet_id": candidate.tweet_id,
                    "query": candidate.query,
                    "proposal_id": proposal["proposal_id"],
                    "proposal_title": draft.title,
                    "rationale": draft.rationale,
                    "candidate": asdict(candidate),
                    "proposal": proposal,
                }
            )
            return proposal

        def fallback() -> dict:
            nonlocal draft, proposal, submitted
            draft = self.policy.build_proposal(candidate)
            if draft is None:
                self._append_log(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "action": "skip_candidate",
                        "agent_name": wallet.agent_name,
                        "account_id": wallet.address.lower(),
                        "tweet_id": candidate.tweet_id,
                        "query": candidate.query,
                        "author": candidate.author,
                        "text": candidate.text,
                    }
                )
                return {"status": "skipped"}
            seed_total = Decimal(draft.yes_liquidity) + Decimal(draft.no_liquidity)
            self.client.ensure_usdnb_ledger_balance(wallet.private_key, seed_total)
            if not submitted:
                proposal = self.client.create_market_review_proposal(
                    wallet.private_key,
                    title=draft.title,
                    description=draft.description,
                    category=draft.category,
                    tags=draft.tags,
                    trading_close_at=(
                        datetime.now(timezone.utc) + timedelta(minutes=draft.trading_close_minutes)
                    ).isoformat(),
                    yes_liquidity=draft.yes_liquidity,
                    no_liquidity=draft.no_liquidity,
                )
                submitted = True
                with self._state_lock:
                    state["submitted_tweet_ids"].append(candidate.tweet_id)
                    state["submitted_proposal_ids"].append(proposal["proposal_id"])
                    self._save_state(state)
                self._append_log(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "action": "submit_market_review_proposal",
                        "auth_mode": "eip712_signed_api",
                        "api_path": "/governance/market-proposals",
                        "agent_name": wallet.agent_name,
                        "account_id": wallet.address.lower(),
                        "tweet_id": candidate.tweet_id,
                        "query": candidate.query,
                        "proposal_id": proposal["proposal_id"],
                        "proposal_title": draft.title,
                        "rationale": draft.rationale,
                        "candidate": asdict(candidate),
                        "proposal": proposal,
                    }
                )
            return proposal or {"status": "skipped"}

        agent.run(
            task="Inspect the X/Twitter candidate, build a concrete prediction-market proposal draft, ensure seed balance exists, and submit exactly one market review proposal if the signal is good enough.",
            context={"candidate": asdict(candidate), "wallet": wallet.agent_name, "account_id": wallet.address.lower()},
            tools=[
                RuntimeTool("build_draft", "Generate a proposal draft from the tweet candidate.", build_draft),
                RuntimeTool("ensure_balance", "Ensure the proposer has enough USDNB seed liquidity in the internal ledger.", ensure_balance),
                RuntimeTool("submit_proposal", "Submit the drafted market review proposal.", submit_proposal),
            ],
            fallback=fallback,
            system_prompt=(
                "You are the EntroMarket proposer agent. "
                "Turn strong X signals into objective market review proposals. "
                "If there is no viable draft, finish without calling submit_proposal."
            ),
        )
        if proposal is not None:
            print(
                f"[proposer] {wallet.agent_name} submitted proposal {proposal['proposal_id']} from tweet {candidate.tweet_id}",
                flush=True,
            )


def load_proposer_wallets(config: ReviewerConfig) -> list[AgentWallet]:
    raw = json.loads(Path(config.participant_wallets_file).read_text(encoding="utf-8"))
    start = max(config.proposer_wallet_start - 1, 0)
    selected = raw[start : start + config.proposer_wallet_count]
    wallets: list[AgentWallet] = []
    for item in selected:
        wallets.append(
            AgentWallet(
                agent_name=str(item["agent_name"]),
                address=str(item["address"]).lower(),
                private_key=str(item["private_key"]),
                erc8004_agent_id=f"{config.proposer_agent_id_prefix}/{item['agent_name']}",
            )
        )
    return wallets
