"""Tests for the directional CPMM service."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from src.amm.service import (
    DirectionalCpmmService,
    LPPosition,
    MarketSide,
    ProbabilitySnapshot,
)


def test_bootstrap_probability_is_balanced() -> None:
    service = DirectionalCpmmService()
    state = service.bootstrap_market("100", "100")
    assert service.probability_yes(state) == Decimal("0.5")


def test_buy_yes_moves_probability_up() -> None:
    service = DirectionalCpmmService()
    state = service.bootstrap_market("100", "100")
    quote = service.buy_yes(state, "10")
    assert quote.probability_yes_after > quote.probability_yes_before
    assert quote.next_state.invariant == state.invariant


def test_buy_no_moves_probability_down() -> None:
    service = DirectionalCpmmService()
    state = service.bootstrap_market("100", "100")
    quote = service.buy_no(state, "10")
    assert quote.probability_yes_after < quote.probability_yes_before
    assert quote.next_state.invariant == state.invariant


def test_add_yes_liquidity_raises_yes_probability() -> None:
    service = DirectionalCpmmService()
    state = service.bootstrap_market("100", "100")
    next_state = service.add_liquidity(state, MarketSide.YES, "50")
    assert service.probability_yes(next_state) > service.probability_yes(state)


def test_information_tax_prefers_earlier_correct_lp() -> None:
    service = DirectionalCpmmService()
    start = datetime(2026, 1, 1, 0, 0, 0)
    resolved_at = start + timedelta(days=1)
    positions = [
        LPPosition(
            provider_id="alice",
            side=MarketSide.YES,
            amount=Decimal("100"),
            entered_at=start,
        ),
        LPPosition(
            provider_id="bob",
            side=MarketSide.YES,
            amount=Decimal("100"),
            entered_at=start + timedelta(hours=18),
        ),
        LPPosition(
            provider_id="carol",
            side=MarketSide.NO,
            amount=Decimal("100"),
            entered_at=start,
        ),
    ]
    snapshots = [
        ProbabilitySnapshot(captured_at=start, probability_yes=Decimal("0.4")),
        ProbabilitySnapshot(captured_at=start + timedelta(hours=6), probability_yes=Decimal("0.45")),
        ProbabilitySnapshot(captured_at=start + timedelta(hours=12), probability_yes=Decimal("0.48")),
        ProbabilitySnapshot(captured_at=start + timedelta(hours=18), probability_yes=Decimal("0.55")),
        ProbabilitySnapshot(captured_at=resolved_at, probability_yes=Decimal("0.8")),
    ]
    rewards = service.allocate_information_tax(
        total_tax=Decimal("1000"),
        positions=positions,
        snapshots=snapshots,
        winning_side=MarketSide.YES,
        resolved_at=resolved_at,
    )
    assert rewards.winner_pool == Decimal("900.00")
    assert rewards.agent_pool == Decimal("50.00")
    assert rewards.treasury_pool == Decimal("50.00")
    assert rewards.rewards_by_provider["alice"] > rewards.rewards_by_provider["bob"]
    assert "carol" not in rewards.rewards_by_provider
