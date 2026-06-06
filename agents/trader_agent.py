from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from chat_runtime import AgentTraceLogger, ChatStyleToolAgent, RuntimeTool
from config import ReviewerConfig
from deepseek_client import DeepSeekClient
from entromarket_client import EntroMarketClient
from models import AgentWallet, ReviewerWallet
from xapi_client import XApiClient


class TraderCluster:
    def __init__(
        self,
        config: ReviewerConfig,
        client: EntroMarketClient,
        xapi_client: XApiClient,
        deepseek_client: DeepSeekClient,
        wallets: list[AgentWallet],
    ) -> None:
        self.config = config
        self.client = client
        self.xapi_client = xapi_client
        self.deepseek_client = deepseek_client
        self.wallets = wallets
        self.config.trader_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.trader_log_path.parent.mkdir(parents=True, exist_ok=True)

    def bootstrap(self) -> None:
        min_usdnb = max(Decimal(str(self.config.trader_order_size)) * Decimal("20"), Decimal("100"))
        min_entropy = max(Decimal(str(self.config.trader_probability_fee)) * Decimal("50"), Decimal("20"))
        #region debug-point trader-bootstrap-start
        self._emit_cluster_debug(
            "debug: trader bootstrap started",
            {
                "wallet_count": len(self.wallets),
                "min_usdnb": str(min_usdnb),
                "min_entropy": str(min_entropy),
            },
        )
        #endregion
        for wallet in self.wallets:
            #region debug-point trader-bootstrap-wallet-start
            self._emit_cluster_debug(
                "debug: trader bootstrap wallet started",
                {"wallet": wallet.agent_name, "address": wallet.address.lower()},
            )
            #endregion
            try:
                #region debug-point trader-bootstrap-usdnb-start
                self._emit_cluster_debug(
                    "debug: trader ensure usdnb started",
                    {"wallet": wallet.agent_name, "required_amount": str(min_usdnb)},
                )
                #endregion
                self.client.ensure_usdnb_ledger_balance(wallet.private_key, min_usdnb)
                #region debug-point trader-bootstrap-usdnb-finished
                self._emit_cluster_debug(
                    "debug: trader ensure usdnb finished",
                    {"wallet": wallet.agent_name},
                )
                #endregion
                #region debug-point trader-bootstrap-entropy-start
                self._emit_cluster_debug(
                    "debug: trader ensure entropy started",
                    {"wallet": wallet.agent_name, "required_amount": str(min_entropy)},
                )
                #endregion
                self.client.ensure_entropy_ledger_balance(wallet.private_key, min_entropy)
                #region debug-point trader-bootstrap-entropy-finished
                self._emit_cluster_debug(
                    "debug: trader ensure entropy finished",
                    {"wallet": wallet.agent_name},
                )
                #endregion
            except Exception as exc:
                #region debug-point trader-bootstrap-wallet-failed
                self._emit_cluster_debug(
                    "debug: trader bootstrap wallet failed",
                    {"wallet": wallet.agent_name, "error": str(exc)},
                )
                #endregion
                self._emit_status(
                    wallet,
                    "启动资金准备失败，先跳过本轮补仓并继续运行。",
                    {"error": str(exc)},
                )
        #region debug-point trader-bootstrap-finished
        self._emit_cluster_debug("debug: trader bootstrap finished", {"wallet_count": len(self.wallets)})
        #endregion

    def run_once(self) -> None:
        #region debug-point trader-run-once-start
        self._emit_cluster_debug(
            "debug: trader run_once started",
            {"wallet_count": len(self.wallets)},
        )
        #endregion
        candidates = self._discover_markets()
        #region debug-point trader-run-once-after-discovery
        self._emit_cluster_debug(
            "debug: trader market discovery completed",
            {"candidate_count": len(candidates)},
        )
        #endregion
        if not candidates:
            print("[trader] no candidate markets found", flush=True)
            for wallet in self.wallets:
                self._emit_status(wallet, "扫描市场中，当前没有可交易机会。", {"candidate_count": 0})
            return
        selected_markets = candidates[: self.config.trader_max_markets_per_cycle]
        for wallet in self.wallets:
            self._emit_status(
                wallet,
                "正在并行观察市场并寻找入场时机。",
                {"market_ids": [market["market_id"] for market in selected_markets]},
            )
        tasks = [
            (wallet, market)
            for wallet in self.wallets
            for market in selected_markets
        ]
        #region debug-point trader-run-once-before-executor
        self._emit_cluster_debug(
            "debug: trader scheduling market tasks",
            {
                "task_count": len(tasks),
                "selected_market_ids": [market["market_id"] for market in selected_markets],
            },
        )
        #endregion
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = [executor.submit(self._run_chat_trader, wallet, market) for wallet, market in tasks]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    #region debug-point trader-run-once-future-error
                    self._emit_cluster_debug(
                        "debug: trader future raised exception",
                        {"error": str(exc)},
                    )
                    #endregion
                    raise
        #region debug-point trader-run-once-finished
        self._emit_cluster_debug(
            "debug: trader run_once finished",
            {"task_count": len(tasks)},
        )
        #endregion

    def watch_forever(self) -> None:
        while True:
            self.run_once()
            self._sleep_with_heartbeat(self.config.trader_poll_interval_seconds)

    def _discover_markets(self) -> list[dict]:
        markets_by_id: dict[str, dict] = {}
        now = datetime.now(timezone.utc)
        try:
            #region debug-point trader-discovery-list-markets-start
            self._emit_cluster_debug("debug: trader list_markets request started", None)
            #endregion
            listed_markets = self.client.list_markets(status="open", limit=100)
            #region debug-point trader-discovery-list-markets-finished
            self._emit_cluster_debug(
                "debug: trader list_markets request finished",
                {"listed_market_count": len(listed_markets)},
            )
            #endregion
        except Exception:
            #region debug-point trader-discovery-list-markets-error
            self._emit_cluster_debug("debug: trader list_markets request failed", None)
            #endregion
            listed_markets = []

        scored_markets: list[tuple[int, dict]] = []
        for item in listed_markets:
            close_at_raw = item.get("trading_close_at")
            if close_at_raw:
                close_at = datetime.fromisoformat(str(close_at_raw).replace("Z", "+00:00")).astimezone(timezone.utc)
                if close_at <= now:
                    continue
            try:
                full_market = self.client.get_market(item["market_id"])
            except Exception:
                continue
            if str(full_market.get("status") or "").lower() != "open":
                continue
            full_close_at_raw = full_market.get("trading_close_at")
            if full_close_at_raw:
                full_close_at = datetime.fromisoformat(str(full_close_at_raw).replace("Z", "+00:00")).astimezone(timezone.utc)
                if full_close_at <= now:
                    continue
            score = self._score_market(full_market)
            scored_markets.append((score, full_market))

        scored_markets.sort(
            key=lambda item: (
                item[0],
                str(item[1].get("created_at") or ""),
            ),
            reverse=True,
        )

        for score, market in scored_markets:
            if score <= 0 and len(markets_by_id) >= self.config.trader_max_markets_per_cycle:
                continue
            markets_by_id[market["market_id"]] = market
        return list(markets_by_id.values())

    def _score_market(self, market: dict) -> int:
        haystack_parts = [
            str(market.get("title") or ""),
            str(market.get("description") or ""),
            str(market.get("category") or ""),
            " ".join(str(item) for item in (market.get("tags") or [])),
        ]
        haystack = " ".join(haystack_parts).lower()
        score = 0
        for query in self.config.trader_search_queries:
            token = str(query).strip().lower()
            if token and token in haystack:
                score += 1
        return score

    def _run_chat_trader(self, wallet: AgentWallet, market: dict) -> None:
        executed_action = "hold"
        logger = AgentTraceLogger(role="trader", agent_name=wallet.agent_name, log_path=self.config.trader_log_path)
        agent = ChatStyleToolAgent(
            role="trader",
            agent_name=wallet.agent_name,
            deepseek_client=self.deepseek_client,
            logger=logger,
        )

        def get_account(_: dict) -> dict:
            account = self.client.get_account(wallet.address)
            return account or {"account_id": wallet.address.lower(), "usdc_balance": "0", "entropy_balance": "0"}

        def get_position(_: dict) -> dict:
            return self.client.get_position(wallet.address, market["market_id"]) or {
                "market_id": market["market_id"],
                "yes_shares": "0",
                "no_shares": "0",
            }

        def search_news(payload: dict) -> dict:
            query = str(payload.get("query") or market["title"]).strip()
            result = self.xapi_client.search_news(query)
            return {
                "query": query,
                "summary": result.summary if result is not None else "No evidence found.",
                "raw": result.raw if result is not None else None,
            }

        def query_probability(_: dict) -> dict:
            required_fee = Decimal(str(self.config.trader_probability_fee))
            self.client.ensure_entropy_ledger_balance(wallet.private_key, required_fee)
            result = self.client.query_probability(
                wallet.private_key,
                market["market_id"],
                self.config.trader_probability_fee,
            )
            self._append_log(wallet, market, "query_probability", result)
            return result

        def buy_yes(payload: dict) -> dict:
            nonlocal executed_action
            share_amount = str(payload.get("share_amount") or self.config.trader_order_size)
            executed_action = "buy_yes"
            result = self.client.buy_yes(wallet.private_key, market["market_id"], share_amount)
            self._append_log(wallet, market, executed_action, result)
            return result

        def buy_no(payload: dict) -> dict:
            nonlocal executed_action
            share_amount = str(payload.get("share_amount") or self.config.trader_order_size)
            executed_action = "buy_no"
            result = self.client.buy_no(wallet.private_key, market["market_id"], share_amount)
            self._append_log(wallet, market, executed_action, result)
            return result

        def sell_yes(payload: dict) -> dict:
            nonlocal executed_action
            share_amount = str(payload.get("share_amount") or self.config.trader_order_size)
            executed_action = "sell_yes"
            result = self.client.sell_yes(wallet.private_key, market["market_id"], share_amount)
            self._append_log(wallet, market, executed_action, result)
            return result

        def sell_no(payload: dict) -> dict:
            nonlocal executed_action
            share_amount = str(payload.get("share_amount") or self.config.trader_order_size)
            executed_action = "sell_no"
            result = self.client.sell_no(wallet.private_key, market["market_id"], share_amount)
            self._append_log(wallet, market, executed_action, result)
            return result

        def add_liquidity(payload: dict) -> dict:
            nonlocal executed_action
            side = str(payload.get("side") or "yes").strip().lower()
            amount = str(payload.get("amount") or self.config.trader_order_size)
            executed_action = f"add_liquidity_{side}"
            result = self.client.add_liquidity(wallet.private_key, market["market_id"], side, amount)
            self._append_log(wallet, market, executed_action, result)
            return result

        def settle(_: dict) -> dict:
            nonlocal executed_action
            executed_action = "settle"
            result = self.client.settle_account(wallet.private_key, market["market_id"])
            self._append_log(wallet, market, executed_action, result)
            return result

        def fallback() -> dict:
            self._append_log(wallet, market, "hold", {"status": "no_trade"})
            return {"action": "hold", "market_id": market["market_id"]}

        agent.run(
            task=(
                "Search the market opportunity, inspect account state, optionally query priced probability, "
                "think about the news catalyst, and then either buy_yes, buy_no, sell_yes, sell_no, add_liquidity, settle, or finish without trading."
            ),
            context={"market": market, "wallet": wallet.agent_name, "default_order_size": self.config.trader_order_size},
            tools=[
                RuntimeTool("get_market", "Fetch the latest market metadata.", lambda _payload: self.client.get_market(market["market_id"])),
                RuntimeTool("get_account", "Fetch the trader account balances.", get_account),
                RuntimeTool("get_position", "Fetch the trader position on this market.", get_position),
                RuntimeTool("search_news", "Search public news related to this market.", search_news),
                RuntimeTool("query_probability", "Pay ENTROPY to fetch the current market probability.", query_probability),
                RuntimeTool("buy_yes", "Buy YES shares on this market.", buy_yes),
                RuntimeTool("buy_no", "Buy NO shares on this market.", buy_no),
                RuntimeTool("sell_yes", "Sell YES shares on this market.", sell_yes),
                RuntimeTool("sell_no", "Sell NO shares on this market.", sell_no),
                RuntimeTool("add_liquidity", "Add directional YES/NO liquidity to this market.", add_liquidity),
                RuntimeTool("settle", "Settle the trader account if the market is resolved.", settle),
            ],
            fallback=fallback,
            system_prompt=(
                "You are a real trading agent for EntroMarket. "
                "Use tools to inspect the market, your balances, and public evidence. "
                "Only trade if the opportunity is strong and the action is justified. "
                "If conviction is low, finish without calling a trade tool."
            ),
        )

    def _append_log(self, wallet: AgentWallet, market: dict, action: str, payload: dict) -> None:
        api_path_by_action = {
            "query_probability": f"/amm/markets/{market['market_id']}/query-probability",
            "buy_yes": f"/amm/markets/{market['market_id']}/accounts/{wallet.address.lower()}/buy-yes",
            "buy_no": f"/amm/markets/{market['market_id']}/accounts/{wallet.address.lower()}/buy-no",
            "sell_yes": f"/amm/markets/{market['market_id']}/accounts/{wallet.address.lower()}/sell-yes",
            "sell_no": f"/amm/markets/{market['market_id']}/accounts/{wallet.address.lower()}/sell-no",
            "add_liquidity_yes": f"/amm/markets/{market['market_id']}/accounts/{wallet.address.lower()}/add-liquidity",
            "add_liquidity_no": f"/amm/markets/{market['market_id']}/accounts/{wallet.address.lower()}/add-liquidity",
            "settle": f"/amm/markets/{market['market_id']}/accounts/{wallet.address.lower()}/settle",
            "hold": None,
        }
        line = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_name": wallet.agent_name,
            "account_id": wallet.address.lower(),
            "market_id": market["market_id"],
            "market_title": market["title"],
            "action": action,
            "auth_mode": "eip712_signed_api" if action != "hold" else None,
            "api_path": api_path_by_action.get(action),
            "payload": payload,
        }
        with self.config.trader_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")

    def _emit_status(self, wallet: AgentWallet, content: str, payload: dict | None = None) -> None:
        AgentTraceLogger(role="trader", agent_name=wallet.agent_name, log_path=self.config.trader_log_path).emit(
            "status",
            content,
            payload,
        )

    def _emit_cluster_debug(self, content: str, payload: dict | None) -> None:
        AgentTraceLogger(role="trader", agent_name="cluster", log_path=self.config.trader_log_path).emit(
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
                self._emit_status(wallet, "在线盯盘中，等待下一次市场扫描。", {"next_cycle_in_seconds": remaining})


def load_trader_wallets(config: ReviewerConfig) -> list[AgentWallet]:
    raw = json.loads(Path(config.participant_wallets_file).read_text(encoding="utf-8"))
    start = max(config.trader_wallet_start - 1, 0)
    selected = raw[start : start + config.trader_wallet_count]
    wallets: list[AgentWallet] = []
    for item in selected:
        wallets.append(
            AgentWallet(
                agent_name=str(item["agent_name"]),
                address=str(item["address"]).lower(),
                private_key=str(item["private_key"]),
                erc8004_agent_id=f"{config.trader_agent_id_prefix}/{item['agent_name']}",
            )
        )
    return wallets
