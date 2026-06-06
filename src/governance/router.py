"""FastAPI router for AI Agent DAO governance."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.amm.router import _to_account_response, _to_market_response
from src.auth.dependencies import require_signed_request
from src.auth.request_service import SignedRequestContext
from src.governance.dependencies import governance_service
from src.governance.schemas import (
    AgentResponse,
    AgentStakeRequest,
    AgentUnstakeRequest,
    ResolutionFallbackRequest,
    ResolutionFallbackResponse,
    MarketReviewFinalizeResponse,
    MarketReviewProposalCreateRequest,
    MarketReviewProposalResponse,
    MarketReviewVoteRequest,
    ResolutionFinalizeResponse,
    ResolutionProposalCreateRequest,
    ResolutionProposalResponse,
    ResolutionVoteRequest,
)
from src.governance.service import MarketReviewProposal, ResolutionProposal, ReviewVote, VetoVote

router = APIRouter(prefix="/governance", tags=["Governance"])


def _to_agent_response(agent_status) -> AgentResponse:
    return AgentResponse(
        account_id=agent_status.profile.account_id,
        controller_address=agent_status.profile.controller_address,
        erc8004_agent_id=agent_status.profile.erc8004_agent_id,
        is_eligible=agent_status.is_eligible,
        registered_at=agent_status.profile.registered_at,
        updated_at=agent_status.profile.updated_at,
        account=_to_account_response(agent_status.account),
    )


def _to_market_review_response(proposal: MarketReviewProposal) -> MarketReviewProposalResponse:
    approve_count = sum(1 for vote in proposal.review_votes.values() if vote == ReviewVote.APPROVE)
    reject_count = sum(1 for vote in proposal.review_votes.values() if vote == ReviewVote.REJECT)
    return MarketReviewProposalResponse(
        proposal_id=proposal.proposal_id,
        proposer_account_id=proposal.proposer_account_id,
        title=proposal.title,
        description=proposal.description,
        category=proposal.category,
        tags=proposal.tags,
        trading_close_at=proposal.trading_close_at,
        yes_liquidity=proposal.yes_liquidity,
        no_liquidity=proposal.no_liquidity,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        status=proposal.status,
        approve_count=approve_count,
        reject_count=reject_count,
        total_votes=len(proposal.review_votes),
        created_market_id=proposal.created_market_id,
        finalized_at=proposal.finalized_at,
        votes=dict(proposal.review_votes),
    )


def _to_resolution_response(proposal: ResolutionProposal) -> ResolutionProposalResponse:
    veto_count = sum(1 for vote in proposal.veto_votes.values() if vote == VetoVote.VETO)
    no_veto_count = sum(1 for vote in proposal.veto_votes.values() if vote == VetoVote.NO_VETO)
    return ResolutionProposalResponse(
        proposal_id=proposal.proposal_id,
        proposer_account_id=proposal.proposer_account_id,
        market_id=proposal.market_id,
        proposed_outcome=proposal.proposed_outcome,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        status=proposal.status,
        veto_count=veto_count,
        no_veto_count=no_veto_count,
        total_votes=len(proposal.veto_votes),
        finalized_at=proposal.finalized_at,
        fallback_outcome=proposal.fallback_outcome,
        fallback_reason=proposal.fallback_reason,
        fallback_finalized_at=proposal.fallback_finalized_at,
        votes=dict(proposal.veto_votes),
    )


@router.get(
    "/agents",
    name="治理 Agent 列表",
    response_model=list[AgentResponse],
)
def list_agents() -> list[AgentResponse]:
    """List all governance agents."""

    return [_to_agent_response(item) for item in governance_service.list_agents()]


@router.get(
    "/agents/{agent_reference:path}",
    name="治理 Agent 详情",
    response_model=AgentResponse,
)
def get_agent(agent_reference: str) -> AgentResponse:
    """Get one governance agent by account id or ERC-8004 agent id."""

    try:
        try:
            agent = governance_service.get_agent_by_erc8004_id(agent_reference)
        except KeyError:
            agent = governance_service.get_agent(agent_reference)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_agent_response(agent)


@router.post(
    "/agents/stake",
    name="治理 Agent 质押",
    response_model=AgentResponse,
)
def stake_agent(
    params: AgentStakeRequest,
    signed_request: SignedRequestContext = Depends(require_signed_request),
) -> AgentResponse:
    """Stake ENTROPY for one governance agent."""

    try:
        agent = governance_service.stake_agent(
            account_id=params.account_id,
            amount=params.amount,
            erc8004_agent_id=params.erc8004_agent_id,
            controller_address=signed_request.account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_agent_response(agent)


@router.post(
    "/agents/unstake",
    name="治理 Agent 解除质押",
    response_model=AgentResponse,
)
def unstake_agent(
    params: AgentUnstakeRequest,
    signed_request: SignedRequestContext = Depends(require_signed_request),
) -> AgentResponse:
    """Unstake ENTROPY for one governance agent."""

    try:
        governance_service.require_account_controller(params.account_id, signed_request.account_id)
        agent = governance_service.unstake_agent(
            account_id=params.account_id,
            amount=params.amount,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_agent_response(agent)


@router.post(
    "/market-proposals",
    name="提交命题审核提案",
    response_model=MarketReviewProposalResponse,
)
def create_market_review_proposal(
    params: MarketReviewProposalCreateRequest,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> MarketReviewProposalResponse:
    """Create a market review proposal before opening a market."""

    proposal = governance_service.submit_market_review_proposal(
        proposer_account_id=params.proposer_account_id,
        title=params.title,
        description=params.description,
        category=params.category,
        tags=params.tags,
        trading_close_at=params.trading_close_at,
        yes_liquidity=params.yes_liquidity,
        no_liquidity=params.no_liquidity,
    )
    return _to_market_review_response(proposal)


@router.get(
    "/market-proposals",
    name="命题审核提案列表",
    response_model=list[MarketReviewProposalResponse],
)
def list_market_review_proposals() -> list[MarketReviewProposalResponse]:
    """List market review proposals."""

    return [_to_market_review_response(item) for item in governance_service.list_market_review_proposals()]


@router.get(
    "/market-proposals/{proposal_id}",
    name="命题审核提案详情",
    response_model=MarketReviewProposalResponse,
)
def get_market_review_proposal(proposal_id: str) -> MarketReviewProposalResponse:
    """Get one market review proposal."""

    try:
        proposal = governance_service.get_market_review_proposal(proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_market_review_response(proposal)


@router.post(
    "/market-proposals/{proposal_id}/votes",
    name="命题审核投票",
    response_model=MarketReviewProposalResponse,
)
def vote_market_review_proposal(
    proposal_id: str,
    params: MarketReviewVoteRequest,
    signed_request: SignedRequestContext = Depends(require_signed_request),
) -> MarketReviewProposalResponse:
    """Vote approve or reject on a market review proposal."""

    try:
        governance_service.require_agent_controller(params.erc8004_agent_id, signed_request.account_id)
        proposal = governance_service.vote_market_review_proposal(
            proposal_id=proposal_id,
            erc8004_agent_id=params.erc8004_agent_id,
            vote=params.vote,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_market_review_response(proposal)


@router.post(
    "/market-proposals/{proposal_id}/finalize",
    name="完成命题审核",
    response_model=MarketReviewFinalizeResponse,
)
def finalize_market_review_proposal(
    proposal_id: str,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> MarketReviewFinalizeResponse:
    """Finalize market review and create the market if approved."""

    try:
        proposal = governance_service.finalize_market_review_proposal(proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    market = None
    if proposal.created_market_id is not None:
        market = governance_service.market_service.get_market(proposal.created_market_id)
    return MarketReviewFinalizeResponse(
        proposal=_to_market_review_response(proposal),
        created_market=_to_market_response(market) if market is not None else None,
    )


@router.post(
    "/resolution-proposals",
    name="提交结算否决提案",
    response_model=ResolutionProposalResponse,
)
def create_resolution_proposal(
    params: ResolutionProposalCreateRequest,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> ResolutionProposalResponse:
    """Create a resolution proposal subject to veto review."""

    try:
        proposal = governance_service.submit_resolution_proposal(
            proposer_account_id=params.proposer_account_id,
            market_id=params.market_id,
            proposed_outcome=params.proposed_outcome,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_resolution_response(proposal)


@router.get(
    "/resolution-proposals",
    name="结算否决提案列表",
    response_model=list[ResolutionProposalResponse],
)
def list_resolution_proposals() -> list[ResolutionProposalResponse]:
    """List resolution proposals."""

    return [_to_resolution_response(item) for item in governance_service.list_resolution_proposals()]


@router.get(
    "/resolution-proposals/{proposal_id}",
    name="结算否决提案详情",
    response_model=ResolutionProposalResponse,
)
def get_resolution_proposal(proposal_id: str) -> ResolutionProposalResponse:
    """Get one resolution proposal."""

    try:
        proposal = governance_service.get_resolution_proposal(proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_resolution_response(proposal)


@router.post(
    "/resolution-proposals/{proposal_id}/votes",
    name="结算否决投票",
    response_model=ResolutionProposalResponse,
)
def vote_resolution_proposal(
    proposal_id: str,
    params: ResolutionVoteRequest,
    signed_request: SignedRequestContext = Depends(require_signed_request),
) -> ResolutionProposalResponse:
    """Vote veto or no_veto on a resolution proposal."""

    try:
        governance_service.require_agent_controller(params.erc8004_agent_id, signed_request.account_id)
        proposal = governance_service.vote_resolution_proposal(
            proposal_id=proposal_id,
            erc8004_agent_id=params.erc8004_agent_id,
            vote=params.vote,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_resolution_response(proposal)


@router.post(
    "/resolution-proposals/{proposal_id}/finalize",
    name="完成结算否决审查",
    response_model=ResolutionFinalizeResponse,
)
def finalize_resolution_proposal(
    proposal_id: str,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> ResolutionFinalizeResponse:
    """Finalize veto review and resolve the market if no veto threshold is met."""

    try:
        proposal, market = governance_service.finalize_resolution_proposal(proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResolutionFinalizeResponse(
        proposal=_to_resolution_response(proposal),
        market=_to_market_response(market) if market is not None else None,
    )


@router.post(
    "/resolution-proposals/{proposal_id}/fallback",
    name="执行结算 fallback 审查",
    response_model=ResolutionFallbackResponse,
)
def apply_resolution_fallback(
    proposal_id: str,
    params: ResolutionFallbackRequest,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> ResolutionFallbackResponse:
    """Apply fallback adjudication to a vetoed resolution proposal."""

    try:
        result = governance_service.apply_resolution_fallback(
            proposal_id=proposal_id,
            final_outcome=params.final_outcome,
            reason=params.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResolutionFallbackResponse(
        proposal=_to_resolution_response(result.proposal),
        market=_to_market_response(result.market),
        slashed_agents=result.slashed_agents,
        rewarded_agents=result.rewarded_agents,
        slashed_total=result.slashed_total,
        rewarded_total=result.rewarded_total,
        retained_treasury=result.retained_treasury,
    )
