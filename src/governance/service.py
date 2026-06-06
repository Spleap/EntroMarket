"""In-memory governance service for the AI Agent DAO flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock
from uuid import uuid4

from src.amm.account_service import Account, InMemoryAccountService
from src.amm.market_service import InMemoryMarketService, Market
from src.amm.service import MarketSide, to_decimal

MIN_AGENT_STAKE = Decimal("100000")
REVIEW_APPROVAL_THRESHOLD = Decimal("0.6666666666666666666666666667")
VETO_THRESHOLD = Decimal("0.4")
REVIEW_QUORUM = 5
VETO_QUORUM = 5
RESOLUTION_SLASH_RATE = Decimal("0.005")


class ReviewVote(str):
    """Review votes for market admission."""

    APPROVE = "approve"
    REJECT = "reject"


class VetoVote(str):
    """Votes for resolution veto review."""

    VETO = "veto"
    NO_VETO = "no_veto"


class ProposalStatus(str):
    """Proposal lifecycle status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    VETOED = "vetoed"
    EXECUTED = "executed"
    FALLBACK_EXECUTED = "fallback_executed"


@dataclass(slots=True)
class AgentProfile:
    """Governance metadata for one AI agent."""

    account_id: str
    controller_address: str
    erc8004_agent_id: str
    registered_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class AgentStakeStatus:
    """Combined agent profile and stake state."""

    profile: AgentProfile
    account: Account
    is_eligible: bool


@dataclass(slots=True)
class MarketReviewProposal:
    """Proposal requesting market creation approval."""

    proposal_id: str
    proposer_account_id: str
    title: str
    description: str | None
    category: str | None
    tags: list[str]
    trading_close_at: datetime
    yes_liquidity: Decimal
    no_liquidity: Decimal
    created_at: datetime
    updated_at: datetime
    status: str
    review_votes: dict[str, str]
    created_market_id: str | None = None
    finalized_at: datetime | None = None


@dataclass(slots=True)
class ResolutionProposal:
    """Proposal requesting final market resolution with veto review."""

    proposal_id: str
    proposer_account_id: str
    market_id: str
    proposed_outcome: MarketSide
    created_at: datetime
    updated_at: datetime
    status: str
    veto_votes: dict[str, str]
    finalized_at: datetime | None = None
    fallback_outcome: MarketSide | None = None
    fallback_reason: str | None = None
    fallback_finalized_at: datetime | None = None


@dataclass(slots=True)
class FallbackAdjudicationResult:
    """Fallback adjudication outcome with slash and reward accounting."""

    proposal: ResolutionProposal
    market: Market
    slashed_agents: dict[str, Decimal]
    rewarded_agents: dict[str, Decimal]
    slashed_total: Decimal
    rewarded_total: Decimal
    retained_treasury: Decimal


class InMemoryGovernanceService:
    """Manage agent staking eligibility and proposal voting."""

    def __init__(
        self,
        market_service: InMemoryMarketService,
        account_service: InMemoryAccountService,
        min_agent_stake: Decimal = MIN_AGENT_STAKE,
        review_quorum: int = REVIEW_QUORUM,
        review_approval_threshold: Decimal = REVIEW_APPROVAL_THRESHOLD,
        veto_quorum: int = VETO_QUORUM,
        veto_threshold: Decimal = VETO_THRESHOLD,
        resolution_slash_rate: Decimal = RESOLUTION_SLASH_RATE,
    ) -> None:
        self.market_service = market_service
        self.account_service = account_service
        self.min_agent_stake = min_agent_stake
        self.review_quorum = review_quorum
        self.review_approval_threshold = review_approval_threshold
        self.veto_quorum = veto_quorum
        self.veto_threshold = veto_threshold
        self.resolution_slash_rate = resolution_slash_rate
        self._agents: dict[str, AgentProfile] = {}
        self._agent_ids: dict[str, str] = {}
        self._market_review_proposals: dict[str, MarketReviewProposal] = {}
        self._resolution_proposals: dict[str, ResolutionProposal] = {}
        self._slashed_entropy_pool = Decimal("0")
        self._rewarded_entropy_total = Decimal("0")
        self._lock = RLock()

    def register_agent(self, account_id: str, erc8004_agent_id: str, controller_address: str) -> AgentProfile:
        """Register or update an agent profile."""

        normalized_agent_id = erc8004_agent_id.strip()
        normalized_controller = controller_address.lower()
        if not normalized_agent_id:
            raise ValueError("erc8004_agent_id is required")
        with self._lock:
            profile = self._agents.get(account_id)
            now = datetime.now(timezone.utc)
            if profile is None:
                existing_account_id = self._agent_ids.get(normalized_agent_id)
                if existing_account_id is not None and existing_account_id != account_id:
                    raise ValueError("erc8004_agent_id is already registered to another agent")
                profile = AgentProfile(
                    account_id=account_id,
                    controller_address=normalized_controller,
                    erc8004_agent_id=normalized_agent_id,
                    registered_at=now,
                    updated_at=now,
                )
                self._agents[account_id] = profile
                self._agent_ids[normalized_agent_id] = account_id
            else:
                if profile.erc8004_agent_id != normalized_agent_id:
                    raise ValueError("agent account is already bound to a different erc8004_agent_id")
                if profile.controller_address != normalized_controller:
                    raise ValueError("agent controller address mismatch")
                profile.updated_at = now
            return profile

    def get_agent(self, account_id: str) -> AgentStakeStatus:
        """Return one agent profile with current stake status."""

        with self._lock:
            profile = self._agents.get(account_id)
            if profile is None:
                raise KeyError(f"agent '{account_id}' not found")
        account = self.account_service.get_or_create_account(account_id)
        return AgentStakeStatus(
            profile=profile,
            account=account,
            is_eligible=self._is_eligible_account(account),
        )

    def get_agent_by_erc8004_id(self, erc8004_agent_id: str) -> AgentStakeStatus:
        """Return one agent profile with current stake status by ERC-8004 id."""

        account_id = self._get_agent_account_id(erc8004_agent_id)
        return self.get_agent(account_id)

    def list_agents(self) -> list[AgentStakeStatus]:
        """Return all registered agents with eligibility state."""

        with self._lock:
            agent_ids = sorted(self._agents.keys())
        return [self.get_agent(account_id) for account_id in agent_ids]

    def stake_agent(self, account_id: str, amount, erc8004_agent_id: str, controller_address: str) -> AgentStakeStatus:
        """Stake ENTROPY for one agent."""

        profile = self.register_agent(
            account_id,
            erc8004_agent_id=erc8004_agent_id,
            controller_address=controller_address,
        )
        account = self.account_service.stake_entropy(account_id, amount)
        return AgentStakeStatus(
            profile=profile,
            account=account,
            is_eligible=self._is_eligible_account(account),
        )

    def unstake_agent(self, account_id: str, amount) -> AgentStakeStatus:
        """Unstake ENTROPY for one agent."""

        with self._lock:
            profile = self._agents.get(account_id)
            if profile is None:
                raise KeyError(f"agent '{account_id}' not found")
        account = self.account_service.unstake_entropy(account_id, amount)
        profile.updated_at = datetime.now(timezone.utc)
        return AgentStakeStatus(
            profile=profile,
            account=account,
            is_eligible=self._is_eligible_account(account),
        )

    def require_agent_controller(self, erc8004_agent_id: str, controller_address: str) -> AgentStakeStatus:
        """Validate that the signer controls the given ERC-8004 agent."""

        status = self.get_agent_by_erc8004_id(erc8004_agent_id)
        if status.profile.controller_address != controller_address.lower():
            raise ValueError("signed account is not authorized for this erc8004 agent")
        return status

    def require_account_controller(self, account_id: str, controller_address: str) -> AgentStakeStatus:
        """Validate that the signer controls the agent account."""

        status = self.get_agent(account_id)
        if status.profile.controller_address != controller_address.lower():
            raise ValueError("signed account is not authorized for this agent account")
        return status

    def submit_market_review_proposal(
        self,
        proposer_account_id: str,
        title: str,
        yes_liquidity,
        no_liquidity,
        description: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        trading_close_at: datetime | None = None,
    ) -> MarketReviewProposal:
        """Create a new market review proposal."""

        now = datetime.now(timezone.utc)
        if trading_close_at is None:
            raise ValueError("trading_close_at is required")
        normalized_close_at = self._normalize_datetime(trading_close_at, "trading_close_at")
        if normalized_close_at <= now:
            raise ValueError("trading_close_at must be in the future")
        yes_liquidity_decimal = to_decimal(yes_liquidity)
        no_liquidity_decimal = to_decimal(no_liquidity)
        if yes_liquidity_decimal != no_liquidity_decimal:
            raise ValueError("initial YES and NO liquidity must be equal")
        proposal = MarketReviewProposal(
            proposal_id=uuid4().hex,
            proposer_account_id=proposer_account_id,
            title=title,
            description=description,
            category=category,
            tags=[tag.strip() for tag in (tags or []) if tag.strip()],
            trading_close_at=normalized_close_at,
            yes_liquidity=yes_liquidity_decimal,
            no_liquidity=no_liquidity_decimal,
            created_at=now,
            updated_at=now,
            status=ProposalStatus.PENDING,
            review_votes={},
        )
        with self._lock:
            self._market_review_proposals[proposal.proposal_id] = proposal
        return proposal

    def list_market_review_proposals(self) -> list[MarketReviewProposal]:
        """List market review proposals in reverse chronological order."""

        with self._lock:
            return sorted(
                self._market_review_proposals.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )

    def get_market_review_proposal(self, proposal_id: str) -> MarketReviewProposal:
        """Return one market review proposal."""

        with self._lock:
            proposal = self._market_review_proposals.get(proposal_id)
            if proposal is None:
                raise KeyError(f"market review proposal '{proposal_id}' not found")
            return proposal

    def vote_market_review_proposal(
        self,
        proposal_id: str,
        erc8004_agent_id: str,
        vote: str,
    ) -> MarketReviewProposal:
        """Cast one review vote on a market proposal."""

        if vote not in {ReviewVote.APPROVE, ReviewVote.REJECT}:
            raise ValueError("invalid review vote")
        self._require_eligible_agent(erc8004_agent_id)
        with self._lock:
            proposal = self._market_review_proposals.get(proposal_id)
            if proposal is None:
                raise KeyError(f"market review proposal '{proposal_id}' not found")
            if proposal.status != ProposalStatus.PENDING:
                raise ValueError("proposal is not pending")
            if erc8004_agent_id in proposal.review_votes:
                raise ValueError("agent already voted on this proposal")
            proposal.review_votes[erc8004_agent_id] = vote
            proposal.updated_at = datetime.now(timezone.utc)
            return proposal

    def finalize_market_review_proposal(self, proposal_id: str) -> MarketReviewProposal:
        """Finalize market review and create the market if approved."""

        with self._lock:
            proposal = self._market_review_proposals.get(proposal_id)
            if proposal is None:
                raise KeyError(f"market review proposal '{proposal_id}' not found")
            if proposal.status != ProposalStatus.PENDING:
                raise ValueError("proposal already finalized")
            total_votes = len(proposal.review_votes)
            approve_votes = sum(1 for vote in proposal.review_votes.values() if vote == ReviewVote.APPROVE)
            approval_ratio = self._safe_ratio(approve_votes, total_votes)
            finalized_at = datetime.now(timezone.utc)
            if proposal.trading_close_at <= finalized_at:
                raise ValueError("proposal trading_close_at has already passed")
            if total_votes >= self.review_quorum and approval_ratio >= self.review_approval_threshold:
                market = self.market_service.create_market(
                    title=proposal.title,
                    description=proposal.description,
                    creator_account_id=proposal.proposer_account_id,
                    category=proposal.category,
                    tags=proposal.tags,
                    trading_close_at=proposal.trading_close_at,
                    yes_liquidity=proposal.yes_liquidity,
                    no_liquidity=proposal.no_liquidity,
                )
                proposal.created_market_id = market.market_id
                proposal.status = ProposalStatus.APPROVED
            else:
                proposal.status = ProposalStatus.REJECTED
            proposal.finalized_at = finalized_at
            proposal.updated_at = finalized_at
            return proposal

    def submit_resolution_proposal(
        self,
        proposer_account_id: str,
        market_id: str,
        proposed_outcome: MarketSide,
    ) -> ResolutionProposal:
        """Create a resolution proposal for an existing market."""

        market = self.market_service.ensure_market_closed_for_resolution(market_id)
        now = datetime.now(timezone.utc)
        proposal = ResolutionProposal(
            proposal_id=uuid4().hex,
            proposer_account_id=proposer_account_id,
            market_id=market_id,
            proposed_outcome=proposed_outcome,
            created_at=now,
            updated_at=now,
            status=ProposalStatus.PENDING,
            veto_votes={},
        )
        with self._lock:
            self._resolution_proposals[proposal.proposal_id] = proposal
        return proposal

    def list_resolution_proposals(self) -> list[ResolutionProposal]:
        """List resolution proposals in reverse chronological order."""

        with self._lock:
            return sorted(
                self._resolution_proposals.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )

    def get_resolution_proposal(self, proposal_id: str) -> ResolutionProposal:
        """Return one resolution proposal."""

        with self._lock:
            proposal = self._resolution_proposals.get(proposal_id)
            if proposal is None:
                raise KeyError(f"resolution proposal '{proposal_id}' not found")
            return proposal

    def vote_resolution_proposal(
        self,
        proposal_id: str,
        erc8004_agent_id: str,
        vote: str,
    ) -> ResolutionProposal:
        """Cast one veto vote on a resolution proposal."""

        if vote not in {VetoVote.VETO, VetoVote.NO_VETO}:
            raise ValueError("invalid veto vote")
        self._require_eligible_agent(erc8004_agent_id)
        with self._lock:
            proposal = self._resolution_proposals.get(proposal_id)
            if proposal is None:
                raise KeyError(f"resolution proposal '{proposal_id}' not found")
            if proposal.status != ProposalStatus.PENDING:
                raise ValueError("proposal is not pending")
            if erc8004_agent_id in proposal.veto_votes:
                raise ValueError("agent already voted on this proposal")
            proposal.veto_votes[erc8004_agent_id] = vote
            proposal.updated_at = datetime.now(timezone.utc)
            return proposal

    def finalize_resolution_proposal(self, proposal_id: str) -> tuple[ResolutionProposal, Market | None]:
        """Finalize veto review and resolve the market if not vetoed."""

        with self._lock:
            proposal = self._resolution_proposals.get(proposal_id)
            if proposal is None:
                raise KeyError(f"resolution proposal '{proposal_id}' not found")
            if proposal.status != ProposalStatus.PENDING:
                raise ValueError("proposal already finalized")
            total_votes = len(proposal.veto_votes)
            veto_votes = sum(1 for vote in proposal.veto_votes.values() if vote == VetoVote.VETO)
            veto_ratio = self._safe_ratio(veto_votes, total_votes)
            finalized_at = datetime.now(timezone.utc)
            proposal.finalized_at = finalized_at
            proposal.updated_at = finalized_at
            if total_votes >= self.veto_quorum and veto_ratio >= self.veto_threshold:
                proposal.status = ProposalStatus.VETOED
                return proposal, None

        market = self.market_service.resolve_market(proposal.market_id, proposal.proposed_outcome)
        with self._lock:
            proposal = self._resolution_proposals[proposal_id]
            proposal.status = ProposalStatus.EXECUTED
            proposal.updated_at = datetime.now(timezone.utc)
            return proposal, market

    def apply_resolution_fallback(
        self,
        proposal_id: str,
        final_outcome: MarketSide,
        reason: str | None = None,
    ) -> FallbackAdjudicationResult:
        """Apply fallback adjudication after a vetoed resolution proposal."""

        with self._lock:
            proposal = self._resolution_proposals.get(proposal_id)
            if proposal is None:
                raise KeyError(f"resolution proposal '{proposal_id}' not found")
            if proposal.status != ProposalStatus.VETOED:
                raise ValueError("fallback can only be applied to vetoed proposals")

        market = self.market_service.resolve_market(proposal.market_id, final_outcome)
        if final_outcome == proposal.proposed_outcome:
            winning_vote = VetoVote.NO_VETO
            losing_vote = VetoVote.VETO
        else:
            winning_vote = VetoVote.VETO
            losing_vote = VetoVote.NO_VETO

        slashed_agents: dict[str, Decimal] = {}
        rewarded_agents: dict[str, Decimal] = {}
        slashed_total = Decimal("0")
        with self._lock:
            current_proposal = self._resolution_proposals[proposal_id]
            for erc8004_agent_id, vote in current_proposal.veto_votes.items():
                if vote != losing_vote:
                    continue
                account_id = self._get_agent_account_id(erc8004_agent_id)
                account = self.account_service.get_account(account_id)
                slash_amount = account.staked_entropy * self.resolution_slash_rate
                if slash_amount <= Decimal("0"):
                    continue
                self.account_service.slash_staked_entropy(account_id, slash_amount)
                slashed_agents[erc8004_agent_id] = slash_amount
                slashed_total += slash_amount

            reward_targets = [
                erc8004_agent_id
                for erc8004_agent_id, vote in current_proposal.veto_votes.items()
                if vote == winning_vote
            ]
            rewarded_total = Decimal("0")
            if reward_targets and slashed_total > Decimal("0"):
                reward_per_agent = slashed_total / Decimal(len(reward_targets))
                for erc8004_agent_id in reward_targets:
                    account_id = self._get_agent_account_id(erc8004_agent_id)
                    self.account_service.deposit_entropy(account_id, reward_per_agent)
                    rewarded_agents[erc8004_agent_id] = reward_per_agent
                    rewarded_total += reward_per_agent
            retained_treasury = slashed_total - rewarded_total
            self._slashed_entropy_pool += retained_treasury
            self._rewarded_entropy_total += rewarded_total
            current_proposal.status = ProposalStatus.FALLBACK_EXECUTED
            current_proposal.fallback_outcome = final_outcome
            current_proposal.fallback_reason = reason
            current_proposal.fallback_finalized_at = datetime.now(timezone.utc)
            current_proposal.updated_at = current_proposal.fallback_finalized_at
            return FallbackAdjudicationResult(
                proposal=current_proposal,
                market=market,
                slashed_agents=slashed_agents,
                rewarded_agents=rewarded_agents,
                slashed_total=slashed_total,
                rewarded_total=rewarded_total,
                retained_treasury=retained_treasury,
            )

    @staticmethod
    def _normalize_datetime(value: datetime, field_name: str) -> datetime:
        if value.tzinfo is None:
            raise ValueError(f"{field_name} must include timezone information")
        return value.astimezone(timezone.utc)

    def _require_eligible_agent(self, erc8004_agent_id: str) -> None:
        account_id = self._get_agent_account_id(erc8004_agent_id)
        account = self.account_service.get_or_create_account(account_id)
        if not self._is_eligible_account(account):
            raise ValueError("agent is not eligible to vote")

    def _is_eligible_account(self, account: Account) -> bool:
        return account.staked_entropy >= self.min_agent_stake

    def _get_agent_account_id(self, erc8004_agent_id: str) -> str:
        with self._lock:
            account_id = self._agent_ids.get(erc8004_agent_id)
            if account_id is None:
                raise ValueError("agent is not registered")
            return account_id

    def _safe_ratio(self, numerator: int, denominator: int) -> Decimal:
        if denominator == 0:
            return Decimal("0")
        return Decimal(numerator) / Decimal(denominator)
