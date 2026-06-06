from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field


@dataclass(slots=True)
class AgentWallet:
    agent_name: str
    address: str
    private_key: str
    erc8004_agent_id: str


ReviewerWallet = AgentWallet


class AgentRole(str, Enum):
    REVIEWER = "reviewer"
    RESOLVER = "resolver"
    PROPOSER = "proposer"
    TRADER = "trader"



@dataclass(slots=True)
class SearchEvidence:
    provider: str
    query: str
    summary: str = ""
    raw: dict | list | None = None


@dataclass(slots=True)
class ReviewDecision:
    vote: str
    summary: str
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: list[SearchEvidence] = field(default_factory=list)

    @property
    def approved(self) -> bool:
        return self.vote == "approve"


@dataclass(slots=True)
class ResolutionAssessment:
    proposed_outcome: str
    vote: str
    rationale: str
    confidence: float
    evidence: list[SearchEvidence] = field(default_factory=list)


@dataclass(slots=True)
class ProposalDraft:
    source_tweet_id: str
    source_query: str
    title: str
    description: str
    category: str
    tags: list[str]
    trading_close_minutes: int
    yes_liquidity: str
    no_liquidity: str
    rationale: str


@dataclass(slots=True)
class AgentTraceEvent:
    role: str
    agent_name: str
    event_type: str
    content: str
    payload: dict | list | None = None


@dataclass(slots=True)
class TraderDecision:
    action: str
    side: str | None
    market_id: str
    title: str
    share_amount: str
    confidence: float
    rationale: str
    evidence: list[SearchEvidence] = field(default_factory=list)
