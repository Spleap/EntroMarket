from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from chat_runtime import AgentTraceLogger, ChatStyleToolAgent, RuntimeTool
from config import ReviewerConfig
from deepseek_client import DeepSeekClient
from entromarket_client import EntroMarketClient
from models import ReviewerWallet
from resolver_policy import ResolverPolicy


class ResolverCluster:
    def __init__(
        self,
        config: ReviewerConfig,
        client: EntroMarketClient,
        policy: ResolverPolicy,
        deepseek_client: DeepSeekClient,
        wallets: list[ReviewerWallet],
    ) -> None:
        self.config = config
        self.client = client
        self.policy = policy
        self.deepseek_client = deepseek_client
        self.wallets = wallets
        self.config.resolver_log_path.parent.mkdir(parents=True, exist_ok=True)

    def bootstrap(self) -> None:
        if not self.config.resolver_auto_bootstrap:
            return
        for wallet in self.wallets:
            self.client.bootstrap_governance_agent(wallet)

    def run_once(self) -> None:
        pending_resolutions = self.client.list_resolution_proposals()
        pending_by_market = {
            item["market_id"]: item
            for item in pending_resolutions
            if item["status"] == "pending"
        }
        all_markets = self.client.list_markets(limit=100)
        closed_markets = [market for market in all_markets if self._is_ready_for_resolution(market)]
        closed_markets = closed_markets[: self.config.resolver_max_markets_per_cycle]
        print(f"[resolver] ready-for-resolution markets: {len(closed_markets)}", flush=True)
        if not closed_markets:
            for wallet in self.wallets:
                self._emit_status(wallet, "巡检中，当前没有可结算市场。", {"ready_market_count": 0})
            return

        for market in closed_markets:
            try:
                proposal = pending_by_market.get(market["market_id"])
                if proposal is None:
                    proposal = self._create_resolution_for_market(market)
                self._vote_resolution(market, proposal)
            except Exception as exc:
                print(f"[resolver] skipped market {market['market_id']}: {exc}", flush=True)

    def watch_forever(self) -> None:
        while True:
            self.run_once()
            self._sleep_with_heartbeat(self.config.resolver_poll_interval_seconds)

    def _create_resolution_for_market(self, market: dict) -> dict:
        proposer = self.wallets[hash(market["market_id"]) % len(self.wallets)]
        assessment = self.policy.assess_market(market)
        logger = AgentTraceLogger(role="resolver", agent_name=proposer.agent_name, log_path=self.config.resolver_log_path)
        agent = ChatStyleToolAgent(
            role="resolver",
            agent_name=proposer.agent_name,
            deepseek_client=self.deepseek_client,
            logger=logger,
        )
        created_payload: dict | None = None

        def assess(_: dict) -> dict:
            latest = self.policy.assess_market(market)
            return {
                "proposed_outcome": latest.proposed_outcome,
                "vote": latest.vote,
                "confidence": latest.confidence,
                "rationale": latest.rationale,
                "evidence": [asdict(item) for item in latest.evidence],
            }

        def create_resolution(payload: dict) -> dict:
            nonlocal created_payload
            outcome = str(payload.get("proposed_outcome") or assessment.proposed_outcome).strip().lower()
            created_payload = self.client.create_resolution_proposal(
                proposer,
                market_id=market["market_id"],
                proposed_outcome=outcome,
            )
            return created_payload

        def fallback() -> dict:
            nonlocal created_payload
            if created_payload is None:
                created_payload = self.client.create_resolution_proposal(
                    proposer,
                    market_id=market["market_id"],
                    proposed_outcome=assessment.proposed_outcome,
                )
            return created_payload

        proposal = agent.run(
            task="Create one defensible resolution proposal for the closed market after checking the deterministic assessment.",
            context={"market": market, "proposer": proposer.agent_name},
            tools=[
                RuntimeTool("get_market", "Fetch the latest market metadata.", lambda _payload: self.client.get_market(market["market_id"])),
                RuntimeTool("assess_market", "Assess the correct market outcome with the resolver policy.", assess),
                RuntimeTool("create_resolution_proposal", "Create the resolution proposal with the chosen outcome.", create_resolution),
            ],
            fallback=fallback,
            system_prompt=(
                "You are a resolver proposer agent for EntroMarket. "
                "Inspect the market, assess the likely outcome, and then create a resolution proposal. "
                "Use create_resolution_proposal exactly once when ready."
            ),
        )
        print(
            f"[resolver] created resolution {proposal['proposal_id']} for market {market['market_id']} "
            f"with outcome={assessment.proposed_outcome}",
            flush=True,
        )
        self._append_log(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "market_id": market["market_id"],
                "market_title": market["title"],
                "action": "create_resolution_proposal",
                "proposal_id": proposal["proposal_id"],
                "proposed_outcome": assessment.proposed_outcome,
                "vote": assessment.vote,
                "confidence": assessment.confidence,
                "rationale": assessment.rationale,
                "evidence": [asdict(item) for item in assessment.evidence],
            }
        )
        return proposal

    def _vote_resolution(self, market: dict, proposal: dict) -> None:
        proposal_id = proposal["proposal_id"]
        eligible_wallets: list[ReviewerWallet] = []
        for wallet in self.wallets:
            latest = self.client.get_resolution_proposal(proposal_id)
            if latest["status"] != "pending":
                break
            if wallet.erc8004_agent_id in latest["votes"]:
                self._emit_status(wallet, "已投过该结算提案，继续监听下一轮。", {"proposal_id": proposal_id})
                continue
            eligible_wallets.append(wallet)

        if eligible_wallets:
            with ThreadPoolExecutor(max_workers=len(eligible_wallets)) as executor:
                futures = [
                    executor.submit(self._run_chat_resolver_vote, wallet=wallet, market=market, proposal_id=proposal_id)
                    for wallet in eligible_wallets
                ]
                for future in as_completed(futures):
                    future.result()

        latest = self.client.get_resolution_proposal(proposal_id)
        if (
            self.config.resolver_auto_finalize
            and latest["status"] == "pending"
            and latest["total_votes"] >= len(self.wallets)
        ):
            finalized = self.client.finalize_resolution_proposal(proposal_id, self.wallets[0])
            market_payload = finalized.get("market")
            market_text = market_payload["market_id"] if market_payload else "market vetoed"
            print(f"[resolver] finalized {proposal_id}: {market_text}", flush=True)

    def _run_chat_resolver_vote(self, wallet: ReviewerWallet, market: dict, proposal_id: str) -> None:
        latest_response: dict | None = None
        submitted_vote = False
        logger = AgentTraceLogger(role="resolver", agent_name=wallet.agent_name, log_path=self.config.resolver_log_path)
        agent = ChatStyleToolAgent(
            role="resolver",
            agent_name=wallet.agent_name,
            deepseek_client=self.deepseek_client,
            logger=logger,
        )

        def assess(_: dict) -> dict:
            current = self.client.get_resolution_proposal(proposal_id)
            assessment = self.policy.vote_for_proposal(market, current)
            return {
                "vote": assessment.vote,
                "proposed_outcome": assessment.proposed_outcome,
                "confidence": assessment.confidence,
                "rationale": assessment.rationale,
                "evidence": [asdict(item) for item in assessment.evidence],
            }

        def submit_vote(payload: dict) -> dict:
            nonlocal submitted_vote, latest_response
            vote = str(payload.get("vote") or "").strip().lower()
            if vote not in {"veto", "no_veto"}:
                raise ValueError("vote must be veto or no_veto")
            latest_response = self.client.vote_resolution_proposal(proposal_id, wallet, vote)
            submitted_vote = True
            assessment = self.policy.vote_for_proposal(market, self.client.get_resolution_proposal(proposal_id))
            self._append_log(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "market_id": market["market_id"],
                    "market_title": market["title"],
                    "proposal_id": proposal_id,
                    "agent_name": wallet.agent_name,
                    "account_id": wallet.address.lower(),
                    "erc8004_agent_id": wallet.erc8004_agent_id,
                    "vote": vote,
                    "proposed_outcome": assessment.proposed_outcome,
                    "confidence": assessment.confidence,
                    "rationale": assessment.rationale,
                    "evidence": [asdict(item) for item in assessment.evidence],
                }
            )
            return latest_response

        def fallback() -> dict:
            nonlocal submitted_vote, latest_response
            assessment = self.policy.vote_for_proposal(market, self.client.get_resolution_proposal(proposal_id))
            if not submitted_vote:
                latest_response = self.client.vote_resolution_proposal(proposal_id, wallet, assessment.vote)
                submitted_vote = True
            self._append_log(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "market_id": market["market_id"],
                    "market_title": market["title"],
                    "proposal_id": proposal_id,
                    "agent_name": wallet.agent_name,
                    "account_id": wallet.address.lower(),
                    "erc8004_agent_id": wallet.erc8004_agent_id,
                    "vote": assessment.vote,
                    "proposed_outcome": assessment.proposed_outcome,
                    "confidence": assessment.confidence,
                    "rationale": assessment.rationale,
                    "evidence": [asdict(item) for item in assessment.evidence],
                }
            )
            return {
                "vote": assessment.vote,
                "response": latest_response or {},
            }

        agent.run(
            task="Review the pending resolution proposal, compare it with your independent assessment, and submit exactly one veto or no_veto vote.",
            context={"market": market, "proposal_id": proposal_id, "wallet": wallet.agent_name},
            tools=[
                RuntimeTool("get_market", "Fetch the latest market metadata.", lambda _payload: self.client.get_market(market["market_id"])),
                RuntimeTool("get_resolution_proposal", "Fetch the latest resolution proposal state.", lambda _payload: self.client.get_resolution_proposal(proposal_id)),
                RuntimeTool("assess_vote", "Compute the recommended veto/no_veto decision.", assess),
                RuntimeTool("submit_vote", "Submit the final veto/no_veto vote.", submit_vote),
            ],
            fallback=fallback,
            system_prompt=(
                "You are a resolver voting agent for EntroMarket. "
                "Inspect the proposal, compare it with your independent assessment, and call submit_vote exactly once when ready."
            ),
        )
        if not submitted_vote:
            fallback()
        if latest_response is not None:
            print(
                f"[resolver] {wallet.agent_name} completed vote on {proposal_id} "
                f"({latest_response.get('veto_count', '?')} veto / {latest_response.get('no_veto_count', '?')} no_veto)",
                flush=True,
            )

    def _append_log(self, payload: dict) -> None:
        with self.config.resolver_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _emit_status(self, wallet: ReviewerWallet, content: str, payload: dict | None = None) -> None:
        AgentTraceLogger(role="resolver", agent_name=wallet.agent_name, log_path=self.config.resolver_log_path).emit(
            "status",
            content,
            payload,
        )

    def _sleep_with_heartbeat(self, total_seconds: int) -> None:
        remaining = max(total_seconds, 0)
        while remaining > 0:
            chunk = min(15, remaining)
            time.sleep(chunk)
            remaining -= chunk
            for wallet in self.wallets:
                self._emit_status(wallet, "在线待命，持续监听市场是否进入裁决窗口。", {"next_cycle_in_seconds": remaining})

    @staticmethod
    def _is_ready_for_resolution(market: dict) -> bool:
        status = str(market.get("status") or "").lower()
        if status == "resolved":
            return False
        close_at = datetime.fromisoformat(str(market["trading_close_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        return close_at <= datetime.now(timezone.utc)


def load_resolver_wallets(config: ReviewerConfig) -> list[ReviewerWallet]:
    raw = json.loads(Path(config.reviewer_wallets_file).read_text(encoding="utf-8"))
    start = max(config.resolver_wallet_start - 1, 0)
    selected = raw[start : start + config.resolver_wallet_count]
    wallets: list[ReviewerWallet] = []
    for item in selected:
        wallets.append(
            ReviewerWallet(
                agent_name=str(item["agent_name"]),
                address=str(item["address"]).lower(),
                private_key=str(item["private_key"]),
                erc8004_agent_id=f"{config.resolver_agent_id_prefix}/{item['agent_name']}",
            )
        )
    return wallets
