from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class AgentRuntimeConfig:
    backend_base_url: str
    sepolia_rpc_url: str
    vault_address: str
    stable_token_address: str
    entropy_token_address: str
    funder_private_key: str | None
    proposer_private_key: str | None
    reviewer_wallets_file: Path
    participant_wallets_file: Path
    reviewer_wallet_start: int
    reviewer_wallet_count: int
    reviewer_agent_id_prefix: str
    reviewer_poll_interval_seconds: int
    reviewer_auto_finalize: bool
    reviewer_auto_bootstrap: bool
    reviewer_min_future_close_seconds: int
    reviewer_log_path: Path
    resolver_wallet_start: int
    resolver_wallet_count: int
    resolver_agent_id_prefix: str
    resolver_poll_interval_seconds: int
    resolver_auto_finalize: bool
    resolver_auto_bootstrap: bool
    resolver_max_markets_per_cycle: int
    resolver_log_path: Path
    proposer_poll_interval_seconds: int
    proposer_wallet_start: int
    proposer_wallet_count: int
    proposer_agent_id_prefix: str
    proposer_search_queries: list[str]
    proposer_max_candidates_per_cycle: int
    proposer_trading_close_minutes: int
    proposer_seed_liquidity: str
    proposer_state_path: Path
    proposer_log_path: Path
    trader_wallet_start: int
    trader_wallet_count: int
    trader_agent_id_prefix: str
    trader_poll_interval_seconds: int
    trader_search_queries: list[str]
    trader_max_markets_per_cycle: int
    trader_order_size: str
    trader_probability_fee: str
    trader_min_edge: float
    trader_state_path: Path
    trader_log_path: Path
    xapi_enabled: bool
    xapi_key: str | None
    xapi_timeout_seconds: int
    deepseek_api_key: str | None
    deepseek_model: str


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


ReviewerConfig = AgentRuntimeConfig


def load_config() -> AgentRuntimeConfig:
    root_env_path = Path(__file__).resolve().parents[1] / ".env"
    if root_env_path.exists():
        load_dotenv(root_env_path)
    env_path = Path(__file__).with_name(".env")
    if env_path.exists():
        load_dotenv(env_path)

    return AgentRuntimeConfig(
        backend_base_url=os.getenv("ENTRO_BACKEND_BASE_URL", "http://165.154.157.75").rstrip("/"),
        sepolia_rpc_url=os.getenv("SEPOLIA_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com"),
        vault_address=os.getenv("ENTRO_VAULT_ADDRESS", "0x725bbDeDd15Dd2bB1eCd2c25D98df80ef3Ff9317"),
        stable_token_address=os.getenv("USDNB_TOKEN_ADDRESS", "0x780B7Cc212335157b925D21Df4501E335b3C1Ac5"),
        entropy_token_address=os.getenv("ENTROPY_TOKEN_ADDRESS", "0x1EAB5C6D71B6BFb831aec956f7468E8b77def64b"),
        funder_private_key=os.getenv("FUNDER_PRIVATE_KEY") or os.getenv("PRIVATE_KEY") or None,
        proposer_private_key=os.getenv("PROPOSER_PRIVATE_KEY") or os.getenv("PRIVATE_KEY") or None,
        reviewer_wallets_file=Path(
            os.getenv(
                "REVIEWER_WALLETS_FILE",
                str(Path(__file__).resolve().parents[1] / "sepolia_agent_wallets.json"),
            )
        ),
        participant_wallets_file=Path(
            os.getenv(
                "PARTICIPANT_WALLETS_FILE",
                str(Path(__file__).resolve().parents[1] / "sepolia_agent_wallets.json"),
            )
        ),
        reviewer_wallet_start=int(os.getenv("REVIEWER_WALLET_START", "1")),
        reviewer_wallet_count=int(os.getenv("REVIEWER_WALLET_COUNT", "5")),
        reviewer_agent_id_prefix=os.getenv("REVIEWER_AGENT_ID_PREFIX", "agent://reviewer-cluster"),
        reviewer_poll_interval_seconds=int(os.getenv("REVIEWER_POLL_INTERVAL_SECONDS", "15")),
        reviewer_auto_finalize=_bool_env("REVIEWER_AUTO_FINALIZE", True),
        reviewer_auto_bootstrap=_bool_env("REVIEWER_AUTO_BOOTSTRAP", True),
        reviewer_min_future_close_seconds=int(os.getenv("REVIEWER_MIN_FUTURE_CLOSE_SECONDS", "300")),
        reviewer_log_path=Path(
            os.getenv(
                "REVIEWER_LOG_PATH",
                str(Path(__file__).resolve().parent / "logs" / "reviewer_activity.jsonl"),
            )
        ),
        resolver_wallet_start=int(os.getenv("RESOLVER_WALLET_START", "6")),
        resolver_wallet_count=int(os.getenv("RESOLVER_WALLET_COUNT", "5")),
        resolver_agent_id_prefix=os.getenv("RESOLVER_AGENT_ID_PREFIX", "agent://resolver-cluster"),
        resolver_poll_interval_seconds=int(os.getenv("RESOLVER_POLL_INTERVAL_SECONDS", "15")),
        resolver_auto_finalize=_bool_env("RESOLVER_AUTO_FINALIZE", True),
        resolver_auto_bootstrap=_bool_env("RESOLVER_AUTO_BOOTSTRAP", True),
        resolver_max_markets_per_cycle=int(os.getenv("RESOLVER_MAX_MARKETS_PER_CYCLE", "3")),
        resolver_log_path=Path(
            os.getenv(
                "RESOLVER_LOG_PATH",
                str(Path(__file__).resolve().parent / "logs" / "resolver_activity.jsonl"),
            )
        ),
        proposer_poll_interval_seconds=int(os.getenv("PROPOSER_POLL_INTERVAL_SECONDS", "60")),
        proposer_wallet_start=int(os.getenv("PROPOSER_WALLET_START", "11")),
        proposer_wallet_count=int(os.getenv("PROPOSER_WALLET_COUNT", "5")),
        proposer_agent_id_prefix=os.getenv("PROPOSER_AGENT_ID_PREFIX", "participant://proposer-cluster"),
        proposer_search_queries=[
            query.strip()
            for query in os.getenv(
                "PROPOSER_SEARCH_QUERIES",
                (
                    "binance listing,coinbase listing,upbit listing,kraken listing,"
                    "mainnet launch,testnet launch,token unlock,airdrop announcement,airdrop snapshot,"
                    "governance proposal,partnership announcement,product release,stablecoin adoption,"
                    "etf approval,sec crypto,fed rate decision,election polling,tesla launch,openai release"
                ),
            ).split(",")
            if query.strip()
        ],
        proposer_max_candidates_per_cycle=int(os.getenv("PROPOSER_MAX_CANDIDATES_PER_CYCLE", "5")),
        proposer_trading_close_minutes=int(os.getenv("PROPOSER_TRADING_CLOSE_MINUTES", "180")),
        proposer_seed_liquidity=os.getenv("PROPOSER_SEED_LIQUIDITY", "20"),
        proposer_state_path=Path(
            os.getenv(
                "PROPOSER_STATE_PATH",
                str(Path(__file__).resolve().parent / "state" / "proposer_state.json"),
            )
        ),
        proposer_log_path=Path(
            os.getenv(
                "PROPOSER_LOG_PATH",
                str(Path(__file__).resolve().parent / "logs" / "proposer_activity.jsonl"),
            )
        ),
        trader_wallet_start=int(os.getenv("TRADER_WALLET_START", "16")),
        trader_wallet_count=int(os.getenv("TRADER_WALLET_COUNT", "5")),
        trader_agent_id_prefix=os.getenv("TRADER_AGENT_ID_PREFIX", "participant://trader-cluster"),
        trader_poll_interval_seconds=int(os.getenv("TRADER_POLL_INTERVAL_SECONDS", "30")),
        trader_search_queries=[
            query.strip()
            for query in os.getenv(
                "TRADER_SEARCH_QUERIES",
                "bitcoin,ethereum,etf,listing,launch,airdrop,mainnet,sec",
            ).split(",")
            if query.strip()
        ],
        trader_max_markets_per_cycle=int(os.getenv("TRADER_MAX_MARKETS_PER_CYCLE", "3")),
        trader_order_size=os.getenv("TRADER_ORDER_SIZE", "10"),
        trader_probability_fee=os.getenv("TRADER_PROBABILITY_FEE", "1"),
        trader_min_edge=float(os.getenv("TRADER_MIN_EDGE", "0.08")),
        trader_state_path=Path(
            os.getenv(
                "TRADER_STATE_PATH",
                str(Path(__file__).resolve().parent / "state" / "trader_state.json"),
            )
        ),
        trader_log_path=Path(
            os.getenv(
                "TRADER_LOG_PATH",
                str(Path(__file__).resolve().parent / "logs" / "trader_activity.jsonl"),
            )
        ),
        xapi_enabled=_bool_env("XAPI_ENABLED", True),
        xapi_key=os.getenv("XAPI_KEY") or None,
        xapi_timeout_seconds=int(os.getenv("XAPI_TIMEOUT_SECONDS", "25")),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or None,
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    )
