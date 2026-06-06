"""Tests for the in-memory market registry service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.amm.market_service import InMemoryMarketService
from src.amm.service import MarketSide


def _future_close_at(minutes: int = 10):
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _create_seeded_market(
    service: InMemoryMarketService,
    title: str = "Demo",
    *,
    creator_account_id: str = "creator-1",
):
    service.account_service.deposit_usdc(creator_account_id, "100000")
    return service.create_market(
        title,
        "100",
        "100",
        creator_account_id=creator_account_id,
        trading_close_at=_future_close_at(),
    )


def test_create_and_list_markets() -> None:
    service = InMemoryMarketService()
    service.account_service.deposit_usdc("creator-1", "100000")
    service.account_service.deposit_usdc("creator-2", "100000")
    first = service.create_market(
        "First",
        "100",
        "100",
        creator_account_id="creator-1",
        category="crypto",
        tags=["btc", "macro"],
        trading_close_at=_future_close_at(),
    )
    second = service.create_market(
        "Second",
        "150",
        "150",
        creator_account_id="creator-2",
        trading_close_at=_future_close_at(),
    )

    markets = service.list_markets()
    market_ids = {market.market_id for market in markets}
    assert market_ids == {first.market_id, second.market_id}
    assert {market.title for market in markets} == {"First", "Second"}
    assert first.creator_account_id == "creator-1"
    assert first.category == "crypto"
    assert first.tags == ["btc", "macro"]


def test_buy_yes_persists_state() -> None:
    service = InMemoryMarketService()
    market = _create_seeded_market(service)

    updated_market, quote = service.buy_yes(market.market_id, "10")
    assert quote.next_state.open_interest_yes == Decimal("10")
    assert updated_market.state.open_interest_yes == Decimal("10")
    assert updated_market.state.reserve_yes == quote.next_state.reserve_yes


def test_query_probability_charges_entropy_and_updates_market_tax() -> None:
    service = InMemoryMarketService()
    market = _create_seeded_market(service)
    service.account_service.deposit_entropy("alice", "10")

    result = service.query_probability(market.market_id, "alice", "1.5")

    assert result.account.entropy_balance == Decimal("8.5")
    assert result.account.total_entropy_spent == Decimal("1.5")
    assert result.market.state.collected_information_tax == Decimal("1.5")
    assert result.probability_yes == Decimal("0.5")


def test_buy_and_sell_for_account_updates_balances_and_positions() -> None:
    service = InMemoryMarketService()
    market = _create_seeded_market(service)
    service.account_service.deposit_usdc("alice", "50")

    buy_result = service.buy_yes_for_account(market.market_id, "alice", "10")
    buy_balance = buy_result.account.usdc_balance
    assert buy_result.account.usdc_balance < Decimal("50")
    assert buy_result.position.yes_shares == Decimal("10")
    assert buy_result.market.state.open_interest_yes == Decimal("10")

    sell_result = service.sell_yes_for_account(market.market_id, "alice", "4")
    assert sell_result.position.yes_shares == Decimal("6")
    assert sell_result.account.usdc_balance > buy_balance


def test_resolve_and_settle_account_position() -> None:
    service = InMemoryMarketService()
    market = _create_seeded_market(service)
    service.account_service.deposit_usdc("alice", "50")

    trade_result = service.buy_yes_for_account(market.market_id, "alice", "5")
    balance_after_buy = trade_result.account.usdc_balance

    market.trading_close_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    resolved_market = service.resolve_market(market.market_id, MarketSide.YES)
    assert resolved_market.status == "resolved"
    assert resolved_market.resolved_outcome == MarketSide.YES

    settlement = service.settle_account(market.market_id, "alice")
    assert settlement.payout == Decimal("5")
    assert settlement.account.usdc_balance == balance_after_buy + Decimal("5")
    assert settlement.position.yes_shares == Decimal("0")
    assert settlement.position.no_shares == Decimal("0")
