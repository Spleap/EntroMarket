"""Tests for the in-memory account ledger."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.amm.account_service import InMemoryAccountService
from src.amm.service import MarketSide


def test_deposit_and_debit_entropy() -> None:
    service = InMemoryAccountService()
    service.deposit_entropy("alice", "25")
    account = service.debit_entropy("alice", "5")

    assert account.entropy_balance == Decimal("20")
    assert account.total_entropy_spent == Decimal("5")
    assert account.query_count == 1


def test_debit_entropy_requires_sufficient_balance() -> None:
    service = InMemoryAccountService()
    service.deposit_entropy("alice", "2")

    with pytest.raises(ValueError, match="insufficient ENTROPY balance"):
        service.debit_entropy("alice", "3")


def test_apply_buy_and_sell_updates_position_and_usdc() -> None:
    service = InMemoryAccountService()
    service.deposit_usdc("alice", "20")

    account_after_buy, position_after_buy = service.apply_buy(
        account_id="alice",
        market_id="market-1",
        side=MarketSide.YES,
        share_amount="5",
        usdc_cost="7.5",
    )
    assert account_after_buy.usdc_balance == Decimal("12.5")
    assert position_after_buy.yes_shares == Decimal("5")

    account_after_sell, position_after_sell = service.apply_sell(
        account_id="alice",
        market_id="market-1",
        side=MarketSide.YES,
        share_amount="2",
        usdc_credit="3",
    )
    assert account_after_sell.usdc_balance == Decimal("15.5")
    assert position_after_sell.yes_shares == Decimal("3")


def test_stake_and_unstake_entropy_updates_balances() -> None:
    service = InMemoryAccountService()
    service.deposit_entropy("alice", "150000")

    account_after_stake = service.stake_entropy("alice", "100000")
    assert account_after_stake.entropy_balance == Decimal("50000")
    assert account_after_stake.staked_entropy == Decimal("100000")

    account_after_unstake = service.unstake_entropy("alice", "25000")
    assert account_after_unstake.entropy_balance == Decimal("75000")
    assert account_after_unstake.staked_entropy == Decimal("75000")


def test_slash_staked_entropy_reduces_locked_balance() -> None:
    service = InMemoryAccountService()
    service.deposit_entropy("alice", "100000")
    service.stake_entropy("alice", "100000")

    account = service.slash_staked_entropy("alice", "500")

    assert account.staked_entropy == Decimal("99500")
    assert account.entropy_balance == Decimal("0")
