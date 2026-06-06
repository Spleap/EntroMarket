"""Pydantic schemas for AI Agent DAO governance."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.amm.schemas import AccountResponse, MarketResponse
from src.amm.service import MarketSide


class AgentStakeRequest(BaseModel):
    account_id: str = Field(..., description="Internal account id used by the agent")
    amount: Decimal = Field(..., description="ENTROPY amount to stake or unstake")
    erc8004_agent_id: str = Field(..., description="ERC-8004 agent identifier")


class AgentUnstakeRequest(BaseModel):
    account_id: str = Field(..., description="Internal account id used by the agent")
    amount: Decimal = Field(..., description="ENTROPY amount to unstake")


class AgentResponse(BaseModel):
    account_id: str
    controller_address: str
    erc8004_agent_id: str
    is_eligible: bool
    registered_at: datetime
    updated_at: datetime
    account: AccountResponse


class MarketReviewProposalCreateRequest(BaseModel):
    proposer_account_id: str = Field(..., description="Account that submits the market review proposal")
    title: str = Field(..., description="Market title")
    description: str | None = Field(default=None, description="Optional market description")
    category: str | None = Field(default=None, description="Optional public category")
    tags: list[str] = Field(default_factory=list, description="Optional public tags for search")
    trading_close_at: datetime = Field(..., description="UTC timestamp when market trading closes")
    yes_liquidity: Decimal = Field(..., description="Initial YES directional liquidity")
    no_liquidity: Decimal = Field(..., description="Initial NO directional liquidity")


class MarketReviewVoteRequest(BaseModel):
    erc8004_agent_id: str = Field(..., description="Registered ERC-8004 agent id")
    vote: str = Field(..., description="approve or reject")


class MarketReviewProposalResponse(BaseModel):
    proposal_id: str
    proposer_account_id: str
    title: str
    description: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    trading_close_at: datetime
    yes_liquidity: Decimal
    no_liquidity: Decimal
    created_at: datetime
    updated_at: datetime
    status: str
    approve_count: int
    reject_count: int
    total_votes: int
    created_market_id: str | None = None
    finalized_at: datetime | None = None
    votes: dict[str, str]


class MarketReviewFinalizeResponse(BaseModel):
    proposal: MarketReviewProposalResponse
    created_market: MarketResponse | None = None


class ResolutionProposalCreateRequest(BaseModel):
    proposer_account_id: str = Field(..., description="Account that submits the resolution proposal")
    market_id: str = Field(..., description="Target market id")
    proposed_outcome: MarketSide = Field(..., description="Proposed final outcome")


class ResolutionVoteRequest(BaseModel):
    erc8004_agent_id: str = Field(..., description="Registered ERC-8004 agent id")
    vote: str = Field(..., description="veto or no_veto")


class ResolutionFallbackRequest(BaseModel):
    final_outcome: MarketSide = Field(..., description="Fallback final outcome")
    reason: str | None = Field(default=None, description="Optional fallback explanation")


class ResolutionProposalResponse(BaseModel):
    proposal_id: str
    proposer_account_id: str
    market_id: str
    proposed_outcome: MarketSide
    created_at: datetime
    updated_at: datetime
    status: str
    veto_count: int
    no_veto_count: int
    total_votes: int
    finalized_at: datetime | None = None
    fallback_outcome: MarketSide | None = None
    fallback_reason: str | None = None
    fallback_finalized_at: datetime | None = None
    votes: dict[str, str]


class ResolutionFinalizeResponse(BaseModel):
    proposal: ResolutionProposalResponse
    market: MarketResponse | None = None


class ResolutionFallbackResponse(BaseModel):
    proposal: ResolutionProposalResponse
    market: MarketResponse
    slashed_agents: dict[str, Decimal]
    rewarded_agents: dict[str, Decimal]
    slashed_total: Decimal
    rewarded_total: Decimal
    retained_treasury: Decimal
