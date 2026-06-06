from __future__ import annotations

import argparse

from deepseek_client import DeepSeekClient
from config import load_config
from entromarket_client import EntroMarketClient
from proposer_agent import ProposerCluster, load_proposer_wallets
from proposer_policy import ProposerPolicy
from reviewer_agent import ReviewerCluster, load_reviewer_wallets
from reviewer_policy import ReviewerPolicy
from resolver_agent import ResolverCluster, load_resolver_wallets
from resolver_policy import ResolverPolicy
from trader_agent import TraderCluster, load_trader_wallets
from xapi_client import XApiClient


def build_reviewer_cluster() -> ReviewerCluster:
    config = load_config()
    wallets = load_reviewer_wallets(config)
    client = EntroMarketClient(config)
    policy = ReviewerPolicy(config)
    xapi_client = XApiClient(
        enabled=config.xapi_enabled,
        api_key=config.xapi_key,
        timeout_seconds=config.xapi_timeout_seconds,
    )
    deepseek_client = DeepSeekClient(
        api_key=config.deepseek_api_key,
        model=config.deepseek_model,
    )
    return ReviewerCluster(
        config=config,
        client=client,
        policy=policy,
        xapi_client=xapi_client,
        deepseek_client=deepseek_client,
        wallets=wallets,
    )


def build_resolver_cluster() -> ResolverCluster:
    config = load_config()
    wallets = load_resolver_wallets(config)
    client = EntroMarketClient(config)
    xapi_client = XApiClient(
        enabled=config.xapi_enabled,
        api_key=config.xapi_key,
        timeout_seconds=config.xapi_timeout_seconds,
    )
    deepseek_client = DeepSeekClient(
        api_key=config.deepseek_api_key,
        model=config.deepseek_model,
    )
    policy = ResolverPolicy(xapi_client=xapi_client, deepseek_client=deepseek_client)
    return ResolverCluster(
        config=config,
        client=client,
        policy=policy,
        deepseek_client=deepseek_client,
        wallets=wallets,
    )


def build_proposer_cluster() -> ProposerCluster:
    config = load_config()
    wallets = load_proposer_wallets(config)
    client = EntroMarketClient(config)
    xapi_client = XApiClient(
        enabled=config.xapi_enabled,
        api_key=config.xapi_key,
        timeout_seconds=config.xapi_timeout_seconds,
    )
    deepseek_client = DeepSeekClient(
        api_key=config.deepseek_api_key,
        model=config.deepseek_model,
    )
    policy = ProposerPolicy(
        deepseek_client=deepseek_client,
        default_close_minutes=config.proposer_trading_close_minutes,
        default_seed_liquidity=config.proposer_seed_liquidity,
    )
    return ProposerCluster(
        config=config,
        client=client,
        policy=policy,
        xapi_client=xapi_client,
        deepseek_client=deepseek_client,
        wallets=wallets,
    )


def build_trader_cluster() -> TraderCluster:
    config = load_config()
    wallets = load_trader_wallets(config)
    client = EntroMarketClient(config)
    xapi_client = XApiClient(
        enabled=config.xapi_enabled,
        api_key=config.xapi_key,
        timeout_seconds=config.xapi_timeout_seconds,
    )
    deepseek_client = DeepSeekClient(
        api_key=config.deepseek_api_key,
        model=config.deepseek_model,
    )
    return TraderCluster(
        config=config,
        client=client,
        xapi_client=xapi_client,
        deepseek_client=deepseek_client,
        wallets=wallets,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Role-based agent cluster for EntroMarket governance.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("reviewer-run-once", help="Run one reviewer polling and voting cycle.")
    subparsers.add_parser("reviewer-watch", help="Continuously watch review proposals and vote.")
    subparsers.add_parser("reviewer-bootstrap", help="Only bootstrap reviewer governance state.")
    subparsers.add_parser("resolver-run-once", help="Run one resolver polling and voting cycle.")
    subparsers.add_parser("resolver-watch", help="Continuously watch closed markets and resolve.")
    subparsers.add_parser("resolver-bootstrap", help="Only bootstrap resolver governance state.")
    subparsers.add_parser("proposer-run-once", help="Run one proposer-cluster discovery and proposal cycle.")
    subparsers.add_parser("proposer-watch", help="Continuously run the proposer participant cluster.")
    subparsers.add_parser("trader-run-once", help="Run one trader discovery and decision cycle.")
    subparsers.add_parser("trader-watch", help="Continuously search markets, think, and trade.")
    args = parser.parse_args()

    if args.command == "reviewer-bootstrap":
        cluster = build_reviewer_cluster()
        cluster.bootstrap()
        print("[reviewer] bootstrap completed", flush=True)
        return
    if args.command == "reviewer-run-once":
        cluster = build_reviewer_cluster()
        cluster.bootstrap()
        cluster.run_once()
        return
    if args.command == "reviewer-watch":
        cluster = build_reviewer_cluster()
        cluster.bootstrap()
        cluster.watch_forever()
        return
    if args.command == "resolver-bootstrap":
        cluster = build_resolver_cluster()
        cluster.bootstrap()
        print("[resolver] bootstrap completed", flush=True)
        return
    if args.command == "resolver-run-once":
        cluster = build_resolver_cluster()
        cluster.bootstrap()
        cluster.run_once()
        return
    if args.command == "proposer-run-once":
        proposer = build_proposer_cluster()
        proposer.bootstrap()
        proposer.run_once()
        return
    if args.command == "proposer-watch":
        proposer = build_proposer_cluster()
        proposer.bootstrap()
        proposer.watch_forever()
        return
    if args.command == "trader-run-once":
        trader = build_trader_cluster()
        trader.bootstrap()
        trader.run_once()
        return
    if args.command == "trader-watch":
        trader = build_trader_cluster()
        trader.bootstrap()
        trader.watch_forever()
        return

    cluster = build_resolver_cluster()
    cluster.bootstrap()
    cluster.watch_forever()


if __name__ == "__main__":
    main()
