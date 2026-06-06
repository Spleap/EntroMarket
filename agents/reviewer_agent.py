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
from reviewer_policy import ReviewerPolicy
from xapi_client import XApiClient


class ReviewerCluster:
    def __init__(
        self,
        config: ReviewerConfig,
        client: EntroMarketClient,
        policy: ReviewerPolicy,
        xapi_client: XApiClient,
        deepseek_client: DeepSeekClient,
        wallets: list[ReviewerWallet],
    ) -> None:
        self.config = config
        self.client = client
        self.policy = policy
        self.xapi_client = xapi_client
        self.deepseek_client = deepseek_client
        self.wallets = wallets
        self.config.reviewer_log_path.parent.mkdir(parents=True, exist_ok=True)

    def bootstrap(self) -> None:
        if not self.config.reviewer_auto_bootstrap:
            return
        for wallet in self.wallets:
            self.client.bootstrap_reviewer(wallet)

    def run_once(self) -> None:
        proposals = self.client.list_market_review_proposals()
        pending = [
            item
            for item in proposals
            if item["status"] == "pending" and not item.get("finalized_at")
        ]
        print(f"[reviewer] pending proposals: {len(pending)}", flush=True)
        if not pending:
            for wallet in self.wallets:
                self._emit_status(wallet, "巡检中，当前没有待审核命题。", {"pending_count": 0})
            return

        for proposal in pending:
            self._process_proposal(proposal)

    def watch_forever(self) -> None:
        while True:
            self.run_once()
            self._sleep_with_heartbeat(self.config.reviewer_poll_interval_seconds)

    def _process_proposal(self, proposal: dict) -> None:
        proposal_id = proposal["proposal_id"]
        print(f"[reviewer] reviewing proposal {proposal_id}: {proposal['title']}", flush=True)
        refreshed = self.client.get_market_review_proposal(proposal_id)
        if refreshed.get("finalized_at"):
            print(f"[reviewer] skipping dirty finalized proposal {proposal_id}", flush=True)
            return
        eligible_wallets: list[ReviewerWallet] = []
        latest = refreshed
        for wallet in self.wallets:
            latest = self.client.get_market_review_proposal(proposal_id)
            if latest["status"] != "pending" or latest.get("finalized_at"):
                break
            if wallet.erc8004_agent_id in latest["votes"]:
                self._emit_status(wallet, "已投过该命题，继续监听下一轮。", {"proposal_id": proposal_id})
                continue
            eligible_wallets.append(wallet)

        if eligible_wallets:
            with ThreadPoolExecutor(max_workers=len(eligible_wallets)) as executor:
                futures = [
                    executor.submit(self._run_chat_reviewer, wallet=wallet, proposal=latest)
                    for wallet in eligible_wallets
                ]
                for future in as_completed(futures):
                    future.result()

        latest = self.client.get_market_review_proposal(proposal_id)
        if (
            self.config.reviewer_auto_finalize
            and latest["status"] == "pending"
            and not latest.get("finalized_at")
            and latest["total_votes"] >= len(self.wallets)
            and latest.get("reject_count", 0) == 0
            and latest.get("approve_count", 0) >= len(self.wallets)
        ):
            finalized = self.client.finalize_market_review(proposal_id, self.wallets[0])
            created_market = finalized.get("created_market")
            market_text = created_market["market_id"] if created_market else "no market created"
            print(f"[reviewer] finalized {proposal_id}: {market_text}", flush=True)

    def _run_chat_reviewer(self, wallet: ReviewerWallet, proposal: dict) -> None:
        proposal_id = proposal["proposal_id"]
        evidence = []
        submitted_vote = False
        latest_response: dict | None = None
        logger = AgentTraceLogger(role="reviewer", agent_name=wallet.agent_name, log_path=self.config.reviewer_log_path)
        agent = ChatStyleToolAgent(
            role="reviewer",
            agent_name=wallet.agent_name,
            deepseek_client=self.deepseek_client,
            logger=logger,
        )

        def search_news(payload: dict) -> dict:
            query = str(payload.get("query") or proposal["title"]).strip()
            #region debug-point reviewer-search-query
            logger.emit(
                "status",
                "debug: reviewer search started",
                {"query": query, "proposal_id": proposal_id, "proposal_title": proposal["title"]},
            )
            #endregion
            result = self.xapi_client.search_news(query)
            if result is not None:
                evidence.append(result)
                raw = result.raw if isinstance(result.raw, dict) else {}
                data = raw.get("data", raw) if isinstance(raw, dict) else {}
                news_items = data.get("news") if isinstance(data, dict) else None
                #region debug-point reviewer-search-result
                logger.emit(
                    "status",
                    "debug: reviewer search finished",
                    {
                        "query": query,
                        "summary": result.summary,
                        "news_count": len(news_items) if isinstance(news_items, list) else None,
                        "raw_top_level_keys": list(raw.keys())[:8] if isinstance(raw, dict) else None,
                        "raw_data_keys": list(data.keys())[:8] if isinstance(data, dict) else None,
                    },
                )
                #endregion
                return asdict(result)
            #region debug-point reviewer-search-none
            logger.emit(
                "status",
                "debug: reviewer search returned none",
                {"query": query},
            )
            #endregion
            return {"query": query, "summary": "No evidence found."}

        def evaluate_policy(_: dict) -> dict:
            decision = self.policy.evaluate(self.client.get_market_review_proposal(proposal_id), evidence=evidence)
            return {
                "vote": decision.vote,
                "summary": decision.summary,
                "blocking_reasons": decision.blocking_reasons,
                "warnings": decision.warnings,
                "evidence": [asdict(item) for item in decision.evidence],
            }

        def submit_vote(payload: dict) -> dict:
            nonlocal submitted_vote, latest_response
            vote = str(payload.get("vote") or "").strip().lower()
            if vote not in {"approve", "reject"}:
                raise ValueError("vote must be approve or reject")
            latest_response = self.client.vote_market_review(proposal_id, wallet, vote)
            submitted_vote = True
            decision = self.policy.evaluate(self.client.get_market_review_proposal(proposal_id), evidence=evidence)
            self._append_log(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "proposal_id": proposal_id,
                    "proposal_title": proposal["title"],
                    "agent_name": wallet.agent_name,
                    "account_id": wallet.address.lower(),
                    "erc8004_agent_id": wallet.erc8004_agent_id,
                    "vote": vote,
                    "summary": decision.summary,
                    "blocking_reasons": decision.blocking_reasons,
                    "warnings": decision.warnings,
                    "evidence": [asdict(item) for item in evidence],
                }
            )
            return latest_response

        def fallback() -> dict:
            nonlocal latest_response, submitted_vote
            if self.policy.should_collect_evidence(proposal) and not evidence:
                try:
                    result = self.xapi_client.search_news(proposal["title"])
                    if result is not None:
                        evidence.append(result)
                except Exception:
                    pass
            decision = self.policy.evaluate(self.client.get_market_review_proposal(proposal_id), evidence=evidence)
            if not submitted_vote:
                latest_response = self.client.vote_market_review(proposal_id, wallet, decision.vote)
                submitted_vote = True
            self._append_log(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "proposal_id": proposal_id,
                    "proposal_title": proposal["title"],
                    "agent_name": wallet.agent_name,
                    "account_id": wallet.address.lower(),
                    "erc8004_agent_id": wallet.erc8004_agent_id,
                    "vote": decision.vote,
                    "summary": decision.summary,
                    "blocking_reasons": decision.blocking_reasons,
                    "warnings": decision.warnings,
                    "evidence": [asdict(item) for item in evidence],
                }
            )
            return {
                "vote": decision.vote,
                "summary": decision.summary,
                "response": latest_response or {},
            }

        result = agent.run(
            task="Review the pending market proposal. Use tools to inspect evidence and policy, then submit exactly one approve or reject vote.",
            context={"proposal": proposal, "wallet": wallet.agent_name},
            tools=[
                RuntimeTool("get_proposal", "Fetch the latest market review proposal state.", lambda _payload: self.client.get_market_review_proposal(proposal_id)),
                RuntimeTool("search_news", "Search public news evidence related to the proposal.", search_news),
                RuntimeTool("evaluate_policy", "Run the deterministic reviewer policy on the proposal and gathered evidence.", evaluate_policy),
                RuntimeTool("submit_vote", "Submit the final approve/reject review vote.", submit_vote),
            ],
            fallback=fallback,
            system_prompt=(
                "You are a reviewer agent for EntroMarket. "
                "Review the proposal carefully, gather evidence if useful, inspect the deterministic policy, "
                "and call submit_vote only when ready. "
                "Never invent facts. If the policy indicates blocking issues, reject."
            ),
        )
        if not submitted_vote:
            fallback()
        if latest_response is not None:
            print(
                f"[reviewer] {wallet.agent_name} completed review on {proposal_id} "
                f"({latest_response.get('approve_count', '?')} approve / {latest_response.get('reject_count', '?')} reject)",
                flush=True,
            )

    def _append_log(self, payload: dict) -> None:
        with self.config.reviewer_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _emit_status(self, wallet: ReviewerWallet, content: str, payload: dict | None = None) -> None:
        AgentTraceLogger(role="reviewer", agent_name=wallet.agent_name, log_path=self.config.reviewer_log_path).emit(
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
                self._emit_status(wallet, "在线待命，持续监听新的审核任务。", {"next_cycle_in_seconds": remaining})


def load_reviewer_wallets(config: ReviewerConfig) -> list[ReviewerWallet]:
    raw = json.loads(Path(config.reviewer_wallets_file).read_text(encoding="utf-8"))
    start = max(config.reviewer_wallet_start - 1, 0)
    selected = raw[start : start + config.reviewer_wallet_count]
    wallets: list[ReviewerWallet] = []
    for item in selected:
        wallets.append(
            ReviewerWallet(
                agent_name=str(item["agent_name"]),
                address=str(item["address"]).lower(),
                private_key=str(item["private_key"]),
                erc8004_agent_id=f"{config.reviewer_agent_id_prefix}/{item['agent_name']}",
            )
        )
    return wallets
