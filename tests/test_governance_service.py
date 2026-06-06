"""Tests for the in-memory AI Agent DAO governance service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.amm.account_service import InMemoryAccountService
from src.amm.market_service import InMemoryMarketService
from src.amm.service import DirectionalCpmmService, MarketSide
from src.governance.service import InMemoryGovernanceService, ReviewVote, VetoVote


def _build_governance_service() -> InMemoryGovernanceService:
    account_service = InMemoryAccountService()
    market_service = InMemoryMarketService(
        amm_service=DirectionalCpmmService(),
        account_service=account_service,
    )
    return InMemoryGovernanceService(
        market_service=market_service,
        account_service=account_service,
    )


def _stake_agents(service: InMemoryGovernanceService, count: int = 5) -> list[str]:
    agent_ids: list[str] = []
    for index in range(count):
        account_id = f"agent-{index}"
        service.account_service.deposit_entropy(account_id, "100000")
        agent_id = f"agent://{index}"
        service.stake_agent(
            account_id,
            "100000",
            erc8004_agent_id=agent_id,
            controller_address=f"0x{index + 1:040x}",
        )
        agent_ids.append(agent_id)
    return agent_ids


def _future_close_at(minutes: int = 10) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def test_stake_agent_becomes_eligible_at_threshold() -> None:
    service = _build_governance_service()
    service.account_service.deposit_entropy("agent-a", "100000")

    status = service.stake_agent(
        "agent-a",
        "100000",
        erc8004_agent_id="agent://alpha",
        controller_address="0x00000000000000000000000000000000000000aa",
    )

    assert status.is_eligible is True
    assert status.account.staked_entropy == Decimal("100000")
    assert status.profile.erc8004_agent_id == "agent://alpha"


def test_market_review_finalize_creates_market_after_quorum() -> None:
    service = _build_governance_service()
    agent_ids = _stake_agents(service)
    proposal = service.submit_market_review_proposal(
        proposer_account_id="creator-1",
        title="ETH above 6000",
        description="Governance review flow",
        trading_close_at=_future_close_at(),
        yes_liquidity="100",
        no_liquidity="100",
    )
    service.account_service.deposit_usdc("creator-1", "200")

    for agent_id in agent_ids:
        service.vote_market_review_proposal(proposal.proposal_id, agent_id, ReviewVote.APPROVE)

    finalized = service.finalize_market_review_proposal(proposal.proposal_id)

    assert finalized.status == "approved"
    assert finalized.created_market_id is not None
    created_market = service.market_service.get_market(finalized.created_market_id)
    assert created_market.title == "ETH above 6000"


def test_market_review_finalize_does_not_mutate_pending_proposal_when_close_has_passed() -> None:
    service = _build_governance_service()
    agent_ids = _stake_agents(service)
    proposal = service.submit_market_review_proposal(
        proposer_account_id="creator-expired",
        title="Expired finalize guard",
        description="Finalize should fail cleanly",
        trading_close_at=_future_close_at(minutes=1),
        yes_liquidity="100",
        no_liquidity="100",
    )
    service.account_service.deposit_usdc("creator-expired", "200")

    for agent_id in agent_ids:
        service.vote_market_review_proposal(proposal.proposal_id, agent_id, ReviewVote.APPROVE)

    proposal.trading_close_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    with pytest.raises(ValueError, match="proposal trading_close_at has already passed"):
        service.finalize_market_review_proposal(proposal.proposal_id)

    reloaded = service.get_market_review_proposal(proposal.proposal_id)
    assert reloaded.status == "pending"
    assert reloaded.created_market_id is None
    assert reloaded.finalized_at is None


def test_resolution_veto_blocks_market_resolution() -> None:
    service = _build_governance_service()
    agent_ids = _stake_agents(service)
    service.account_service.deposit_usdc("creator-2", "200")
    market = service.market_service.create_market(
        title="BTC above 200k",
        creator_account_id="creator-2",
        trading_close_at=_future_close_at(),
        yes_liquidity="100",
        no_liquidity="100",
    )
    market.trading_close_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    proposal = service.submit_resolution_proposal(
        proposer_account_id="resolver-1",
        market_id=market.market_id,
        proposed_outcome=MarketSide.YES,
    )

    for agent_id in agent_ids:
        service.vote_resolution_proposal(proposal.proposal_id, agent_id, VetoVote.VETO)

    finalized, resolved_market = service.finalize_resolution_proposal(proposal.proposal_id)

    assert finalized.status == "vetoed"
    assert resolved_market is None
    assert service.market_service.get_market(market.market_id).status == "closed"


def test_resolution_fallback_slashes_wrong_voters_and_rewards_correct_voters() -> None:
    service = _build_governance_service()
    agent_ids = _stake_agents(service)
    service.account_service.deposit_usdc("creator-3", "200")
    market = service.market_service.create_market(
        title="ETH above 8k",
        creator_account_id="creator-3",
        trading_close_at=_future_close_at(),
        yes_liquidity="100",
        no_liquidity="100",
    )
    market.trading_close_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    proposal = service.submit_resolution_proposal(
        proposer_account_id="resolver-2",
        market_id=market.market_id,
        proposed_outcome=MarketSide.YES,
    )

    for agent_id in agent_ids[:3]:
        service.vote_resolution_proposal(proposal.proposal_id, agent_id, VetoVote.VETO)
    for agent_id in agent_ids[3:]:
        service.vote_resolution_proposal(proposal.proposal_id, agent_id, VetoVote.NO_VETO)

    finalized, resolved_market = service.finalize_resolution_proposal(proposal.proposal_id)
    assert finalized.status == "vetoed"
    assert resolved_market is None

    fallback = service.apply_resolution_fallback(
        proposal_id=proposal.proposal_id,
        final_outcome=MarketSide.NO,
        reason="Fallback oracle confirms NO",
    )

    assert fallback.proposal.status == "fallback_executed"
    assert fallback.market.status == "resolved"
    assert fallback.market.resolved_outcome == MarketSide.NO
    assert fallback.slashed_total == Decimal("1000.000")
    assert fallback.rewarded_total == Decimal("999.9999999999999999999999999")
    assert fallback.retained_treasury == Decimal("0.0000000000000000000000001")
    assert len(fallback.rewarded_agents) == 3
    assert len(fallback.slashed_agents) == 2
