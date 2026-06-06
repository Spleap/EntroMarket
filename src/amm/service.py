"""CPMM variant domain logic for a directional prediction market."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, getcontext
from enum import Enum
from typing import Iterable

getcontext().prec = 28

ZERO = Decimal("0")
ONE = Decimal("1")


def to_decimal(value: Decimal | str | int | float) -> Decimal:
    """Convert external input into Decimal without float precision drift."""

    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


class MarketSide(str, Enum):
    """Allowed market sides."""

    YES = "yes"
    NO = "no"


@dataclass(slots=True)
class MarketConfig:
    """Static market parameters."""

    alpha: Decimal = Decimal("100")
    beta: Decimal = Decimal("1")
    trade_fee_rate: Decimal = Decimal("0.003")
    winning_lp_ratio: Decimal = Decimal("0.90")
    agent_ratio: Decimal = Decimal("0.05")
    treasury_ratio: Decimal = Decimal("0.05")
    warmup_seconds: int = 0
    lp_cutoff_seconds: int = 0
    risk_multiplier: Decimal = Decimal("0.5")

    def validate(self) -> None:
        """Validate configuration invariants."""

        if self.alpha <= ZERO:
            raise ValueError("alpha must be positive")
        if self.beta <= ZERO:
            raise ValueError("beta must be positive")
        if not (ZERO <= self.trade_fee_rate < ONE):
            raise ValueError("trade_fee_rate must be in [0, 1)")
        total_ratio = self.winning_lp_ratio + self.agent_ratio + self.treasury_ratio
        if total_ratio != ONE:
            raise ValueError("information tax ratios must sum to 1")
        if self.warmup_seconds < 0:
            raise ValueError("warmup_seconds must be non-negative")
        if self.lp_cutoff_seconds < 0:
            raise ValueError("lp_cutoff_seconds must be non-negative")
        if self.risk_multiplier < ZERO:
            raise ValueError("risk_multiplier must be non-negative")


@dataclass(slots=True)
class MarketState:
    """Current AMM state."""

    yes_liquidity: Decimal
    no_liquidity: Decimal
    reserve_yes: Decimal
    reserve_no: Decimal
    invariant: Decimal
    collected_trading_fee: Decimal = ZERO
    collected_collateral: Decimal = ZERO
    open_interest_yes: Decimal = ZERO
    open_interest_no: Decimal = ZERO
    collected_information_tax: Decimal = ZERO


@dataclass(slots=True)
class TradeQuote:
    """Quote and resulting state after a trade."""

    side: MarketSide
    share_delta: Decimal
    base_cost: Decimal
    fee: Decimal
    total_amount: Decimal
    probability_yes_before: Decimal
    probability_yes_after: Decimal
    next_state: MarketState


@dataclass(slots=True)
class LPPosition:
    """Directional LP contribution tracked for information tax."""

    provider_id: str
    side: MarketSide
    amount: Decimal
    entered_at: datetime


@dataclass(slots=True)
class ProbabilitySnapshot:
    """Market probability snapshot used for score integration."""

    captured_at: datetime
    probability_yes: Decimal


@dataclass(slots=True)
class RewardBreakdown:
    """Final information tax allocation."""

    winner_pool: Decimal
    agent_pool: Decimal
    treasury_pool: Decimal
    rewards_by_provider: dict[str, Decimal]


class DirectionalCpmmService:
    """Service layer for the directional CPMM market."""

    def __init__(self, config: MarketConfig | None = None) -> None:
        self.config = config or MarketConfig()
        self.config.validate()

    def bootstrap_market(
        self,
        yes_liquidity: Decimal | str | int,
        no_liquidity: Decimal | str | int,
    ) -> MarketState:
        """Create an initial market state from one-sided LP capital."""

        yes_liquidity_decimal = self._require_positive(yes_liquidity, "yes_liquidity")
        no_liquidity_decimal = self._require_positive(no_liquidity, "no_liquidity")
        reserve_yes = self.config.alpha + (self.config.beta * yes_liquidity_decimal)
        reserve_no = self.config.alpha + (self.config.beta * no_liquidity_decimal)
        invariant = reserve_yes * reserve_no
        return MarketState(
            yes_liquidity=yes_liquidity_decimal,
            no_liquidity=no_liquidity_decimal,
            reserve_yes=reserve_yes,
            reserve_no=reserve_no,
            invariant=invariant,
        )

    def probability_yes(self, state: MarketState) -> Decimal:
        """Return the current YES implied probability."""

        total = state.reserve_yes + state.reserve_no
        if total <= ZERO:
            raise ValueError("total reserve must be positive")
        return state.reserve_yes / total

    def add_liquidity(
        self,
        state: MarketState,
        side: MarketSide,
        amount: Decimal | str | int,
    ) -> MarketState:
        """Add directional liquidity and rebuild the virtual invariant."""

        liquidity = self._require_positive(amount, "amount")
        next_state = self._clone_state(state)
        if side == MarketSide.YES:
            next_state.yes_liquidity += liquidity
            next_state.reserve_yes += self.config.beta * liquidity
        else:
            next_state.no_liquidity += liquidity
            next_state.reserve_no += self.config.beta * liquidity
        next_state.invariant = next_state.reserve_yes * next_state.reserve_no
        return next_state

    def buy_yes(self, state: MarketState, share_amount: Decimal | str | int) -> TradeQuote:
        """Buy YES shares using the CPMM invariant."""

        share_delta = self._require_trade_size(share_amount, state.reserve_no, "share_amount")
        probability_before = self.probability_yes(state)
        reserve_no_after = state.reserve_no - share_delta
        reserve_yes_after = state.invariant / reserve_no_after
        base_cost = reserve_yes_after - state.reserve_yes
        fee = base_cost * self.config.trade_fee_rate
        next_state = self._clone_state(state)
        next_state.reserve_yes = reserve_yes_after
        next_state.reserve_no = reserve_no_after
        next_state.invariant = state.invariant
        next_state.collected_trading_fee += fee
        next_state.collected_collateral += base_cost + fee
        next_state.open_interest_yes += share_delta
        probability_after = self.probability_yes(next_state)
        return TradeQuote(
            side=MarketSide.YES,
            share_delta=share_delta,
            base_cost=base_cost,
            fee=fee,
            total_amount=base_cost + fee,
            probability_yes_before=probability_before,
            probability_yes_after=probability_after,
            next_state=next_state,
        )

    def buy_no(self, state: MarketState, share_amount: Decimal | str | int) -> TradeQuote:
        """Buy NO shares using the CPMM invariant."""

        share_delta = self._require_trade_size(share_amount, state.reserve_yes, "share_amount")
        probability_before = self.probability_yes(state)
        reserve_yes_after = state.reserve_yes - share_delta
        reserve_no_after = state.invariant / reserve_yes_after
        base_cost = reserve_no_after - state.reserve_no
        fee = base_cost * self.config.trade_fee_rate
        next_state = self._clone_state(state)
        next_state.reserve_yes = reserve_yes_after
        next_state.reserve_no = reserve_no_after
        next_state.invariant = state.invariant
        next_state.collected_trading_fee += fee
        next_state.collected_collateral += base_cost + fee
        next_state.open_interest_no += share_delta
        probability_after = self.probability_yes(next_state)
        return TradeQuote(
            side=MarketSide.NO,
            share_delta=share_delta,
            base_cost=base_cost,
            fee=fee,
            total_amount=base_cost + fee,
            probability_yes_before=probability_before,
            probability_yes_after=probability_after,
            next_state=next_state,
        )

    def sell_yes(self, state: MarketState, share_amount: Decimal | str | int) -> TradeQuote:
        """Sell YES shares back into the pool."""

        share_delta = self._require_positive(share_amount, "share_amount")
        if share_delta > state.open_interest_yes:
            raise ValueError("cannot sell more YES shares than open interest")
        probability_before = self.probability_yes(state)
        reserve_yes_after = state.reserve_yes + share_delta
        reserve_no_after = state.invariant / reserve_yes_after
        base_payout = state.reserve_no - reserve_no_after
        fee = base_payout * self.config.trade_fee_rate
        next_state = self._clone_state(state)
        next_state.reserve_yes = reserve_yes_after
        next_state.reserve_no = reserve_no_after
        next_state.invariant = state.invariant
        next_state.collected_trading_fee += fee
        next_state.collected_collateral -= base_payout - fee
        next_state.open_interest_yes -= share_delta
        probability_after = self.probability_yes(next_state)
        return TradeQuote(
            side=MarketSide.YES,
            share_delta=share_delta,
            base_cost=base_payout,
            fee=fee,
            total_amount=base_payout - fee,
            probability_yes_before=probability_before,
            probability_yes_after=probability_after,
            next_state=next_state,
        )

    def sell_no(self, state: MarketState, share_amount: Decimal | str | int) -> TradeQuote:
        """Sell NO shares back into the pool."""

        share_delta = self._require_positive(share_amount, "share_amount")
        if share_delta > state.open_interest_no:
            raise ValueError("cannot sell more NO shares than open interest")
        probability_before = self.probability_yes(state)
        reserve_no_after = state.reserve_no + share_delta
        reserve_yes_after = state.invariant / reserve_no_after
        base_payout = state.reserve_yes - reserve_yes_after
        fee = base_payout * self.config.trade_fee_rate
        next_state = self._clone_state(state)
        next_state.reserve_yes = reserve_yes_after
        next_state.reserve_no = reserve_no_after
        next_state.invariant = state.invariant
        next_state.collected_trading_fee += fee
        next_state.collected_collateral -= base_payout - fee
        next_state.open_interest_no -= share_delta
        probability_after = self.probability_yes(next_state)
        return TradeQuote(
            side=MarketSide.NO,
            share_delta=share_delta,
            base_cost=base_payout,
            fee=fee,
            total_amount=base_payout - fee,
            probability_yes_before=probability_before,
            probability_yes_after=probability_after,
            next_state=next_state,
        )

    def allocate_information_tax(
        self,
        total_tax: Decimal | str | int,
        positions: Iterable[LPPosition],
        snapshots: Iterable[ProbabilitySnapshot],
        winning_side: MarketSide,
        resolved_at: datetime,
    ) -> RewardBreakdown:
        """Allocate information tax using time and risk weighted scores."""

        total_tax_decimal = self._require_non_negative(total_tax, "total_tax")
        ordered_snapshots = sorted(snapshots, key=lambda item: item.captured_at)
        if not ordered_snapshots:
            raise ValueError("at least one probability snapshot is required")

        score_by_provider: dict[str, Decimal] = {}
        for position in positions:
            if position.side != winning_side:
                continue
            probability_yes = self._find_probability_for_position(ordered_snapshots, position.entered_at, resolved_at)
            if winning_side == MarketSide.YES:
                risk_weight = ONE + (self.config.risk_multiplier * (ONE - probability_yes))
            else:
                risk_weight = ONE + (self.config.risk_multiplier * probability_yes)
            score = position.amount * risk_weight
            if score > ZERO:
                score_by_provider[position.provider_id] = score_by_provider.get(position.provider_id, ZERO) + score

        winner_pool = total_tax_decimal * self.config.winning_lp_ratio
        total_score = sum(score_by_provider.values(), ZERO)
        rewards: dict[str, Decimal] = {}
        if total_score > ZERO:
            for provider_id, score in score_by_provider.items():
                rewards[provider_id] = winner_pool * score / total_score

        return RewardBreakdown(
            winner_pool=winner_pool,
            agent_pool=total_tax_decimal * self.config.agent_ratio,
            treasury_pool=total_tax_decimal * self.config.treasury_ratio,
            rewards_by_provider=rewards,
        )

    def _find_probability_for_position(
        self,
        ordered_snapshots: list[ProbabilitySnapshot],
        entered_at: datetime,
        resolved_at: datetime,
    ) -> Decimal:
        candidate = ordered_snapshots[0].probability_yes
        for snapshot in ordered_snapshots:
            if snapshot.captured_at <= entered_at:
                candidate = snapshot.probability_yes
                continue
            break
        if entered_at > resolved_at:
            return ordered_snapshots[-1].probability_yes
        return candidate

    def _clone_state(self, state: MarketState) -> MarketState:
        return MarketState(
            yes_liquidity=state.yes_liquidity,
            no_liquidity=state.no_liquidity,
            reserve_yes=state.reserve_yes,
            reserve_no=state.reserve_no,
            invariant=state.invariant,
            collected_trading_fee=state.collected_trading_fee,
            collected_collateral=state.collected_collateral,
            open_interest_yes=state.open_interest_yes,
            open_interest_no=state.open_interest_no,
            collected_information_tax=state.collected_information_tax,
        )

    def _require_positive(self, value: Decimal | str | int, field_name: str) -> Decimal:
        decimal_value = to_decimal(value)
        if decimal_value <= ZERO:
            raise ValueError(f"{field_name} must be positive")
        return decimal_value

    def _require_non_negative(self, value: Decimal | str | int, field_name: str) -> Decimal:
        decimal_value = to_decimal(value)
        if decimal_value < ZERO:
            raise ValueError(f"{field_name} must be non-negative")
        return decimal_value

    def _require_trade_size(
        self,
        share_amount: Decimal | str | int,
        remaining_reserve: Decimal,
        field_name: str,
    ) -> Decimal:
        decimal_value = self._require_positive(share_amount, field_name)
        if decimal_value >= remaining_reserve:
            raise ValueError("trade is too large for current reserve depth")
        return decimal_value
