"""Pydantic schemas for the AMM demo endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.amm.service import MarketSide


class BootstrapRequest(BaseModel):
    yes_liquidity: Decimal = Field(..., description="Initial YES directional liquidity")
    no_liquidity: Decimal = Field(..., description="Initial NO directional liquidity")


class CreateMarketRequest(BootstrapRequest):
    title: str = Field(..., description="Human readable market title")
    description: str | None = Field(default=None, description="Optional market description")
    creator_account_id: str | None = Field(default=None, description="Optional market creator account id")
    category: str | None = Field(default=None, description="Optional market category for free browsing")
    tags: list[str] = Field(default_factory=list, description="Optional public tags for market search")
    trading_close_at: datetime = Field(..., description="UTC timestamp when market trading closes")


class MarketStateResponse(BaseModel):
    yes_liquidity: Decimal
    no_liquidity: Decimal
    reserve_yes: Decimal
    reserve_no: Decimal
    invariant: Decimal
    probability_yes: Decimal
    collected_trading_fee: Decimal
    collected_collateral: Decimal
    collected_information_tax: Decimal
    open_interest_yes: Decimal
    open_interest_no: Decimal


class AccountResponse(BaseModel):
    account_id: str
    usdc_balance: Decimal
    entropy_balance: Decimal
    staked_entropy: Decimal
    total_entropy_spent: Decimal
    query_count: int
    created_at: datetime
    updated_at: datetime


class PositionResponse(BaseModel):
    account_id: str
    market_id: str
    yes_shares: Decimal
    no_shares: Decimal
    created_at: datetime
    updated_at: datetime


class LiquidityPositionResponse(BaseModel):
    lp_id: str
    provider_id: str
    market_id: str
    side: MarketSide
    amount: Decimal
    entered_at: datetime
    updated_at: datetime


class MarketResponse(BaseModel):
    market_id: str
    title: str
    description: str | None = None
    creator_account_id: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    trading_close_at: datetime
    updated_at: datetime
    status: str
    resolved_outcome: MarketSide | None = None
    resolved_at: datetime | None = None
    state: MarketStateResponse


class PublicMarketResponse(BaseModel):
    market_id: str
    title: str
    description: str | None = None
    creator_account_id: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    trading_close_at: datetime
    updated_at: datetime
    status: str
    resolved_outcome: MarketSide | None = None
    resolved_at: datetime | None = None


class TradeRequest(BaseModel):
    state: MarketStateResponse
    share_amount: Decimal = Field(..., description="Trade size in share units")


class StoredTradeRequest(BaseModel):
    share_amount: Decimal = Field(..., description="Trade size in share units")


class AddLiquidityRequest(BaseModel):
    state: MarketStateResponse
    side: MarketSide
    amount: Decimal = Field(..., description="Directional LP amount")


class StoredAddLiquidityRequest(BaseModel):
    side: MarketSide
    amount: Decimal = Field(..., description="Directional LP amount")


class DepositRequest(BaseModel):
    amount: Decimal = Field(..., description="Amount to deposit into the internal ledger")


class ProbabilityQueryRequest(BaseModel):
    account_id: str = Field(..., description="Internal account identifier")
    entropy_fee: Decimal = Field(..., description="ENTROPY fee charged for this query")


class ResolveMarketRequest(BaseModel):
    outcome: MarketSide = Field(..., description="Final resolved outcome")


class AccountTradeRequest(BaseModel):
    share_amount: Decimal = Field(..., description="Trade size in share units")


class SessionTradeRequest(BaseModel):
    session_id: str = Field(..., description="Delegated session identifier")
    share_amount: Decimal = Field(..., description="Trade size in share units")


class TradeResponse(BaseModel):
    side: MarketSide
    share_delta: Decimal
    base_cost: Decimal
    fee: Decimal
    total_amount: Decimal
    probability_yes_before: Decimal
    probability_yes_after: Decimal
    next_state: MarketStateResponse


class StoredTradeResponse(BaseModel):
    market: MarketResponse
    trade: TradeResponse


class ProbabilityQueryResponse(BaseModel):
    market: MarketResponse
    account: AccountResponse
    probability_yes: Decimal
    entropy_fee_charged: Decimal


class AccountTradeResponse(BaseModel):
    market: MarketResponse
    account: AccountResponse
    position: PositionResponse
    trade: TradeResponse


class AccountLiquidityResponse(BaseModel):
    market: MarketResponse
    account: AccountResponse
    lp_position: LiquidityPositionResponse


class SettlementResponse(BaseModel):
    market: MarketResponse
    account: AccountResponse
    position: PositionResponse
    payout: Decimal


class SessionProbabilityQueryRequest(BaseModel):
    session_id: str = Field(..., description="Delegated session identifier")
    entropy_fee: Decimal = Field(..., description="ENTROPY fee charged for this query")


class LPPositionPayload(BaseModel):
    provider_id: str
    side: MarketSide
    amount: Decimal
    entered_at: datetime


class ProbabilitySnapshotPayload(BaseModel):
    captured_at: datetime
    probability_yes: Decimal


class InformationTaxRequest(BaseModel):
    total_tax: Decimal
    winning_side: MarketSide
    resolved_at: datetime
    positions: list[LPPositionPayload]
    snapshots: list[ProbabilitySnapshotPayload]


class InformationTaxResponse(BaseModel):
    winner_pool: Decimal
    agent_pool: Decimal
    treasury_pool: Decimal
    rewards_by_provider: dict[str, Decimal]
