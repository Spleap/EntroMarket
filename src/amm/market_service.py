"""In-memory market registry built on top of the AMM math service."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime, timezone
from decimal import Decimal
from threading import Lock
from uuid import uuid4

from src.amm.account_service import Account, InMemoryAccountService, Position
from src.market_index.service import SQLiteMarketIndexService
from src.amm.service import (
    DirectionalCpmmService,
    LPPosition as RewardLPPosition,
    MarketSide,
    MarketState,
    ProbabilitySnapshot,
    TradeQuote,
    ZERO,
    to_decimal,
)


class MarketLifecycle(str):
    """Market lifecycle states."""

    OPEN = "open"
    CLOSED = "closed"
    RESOLVED = "resolved"


@dataclass(slots=True)
class Market:
    """Runtime market entity stored in memory."""

    market_id: str
    title: str
    description: str | None
    creator_account_id: str | None
    category: str | None
    tags: list[str]
    created_at: datetime
    trading_close_at: datetime
    updated_at: datetime
    state: MarketState
    status: str = MarketLifecycle.OPEN
    resolved_outcome: MarketSide | None = None
    resolved_at: datetime | None = None
    settled_accounts: set[str] = field(default_factory=set)
    lp_fee_rewards: dict[str, Decimal] = field(default_factory=dict)
    lp_principal_returns: dict[str, Decimal] = field(default_factory=dict)
    agent_reward_pool: Decimal = ZERO
    treasury_reward_pool: Decimal = ZERO


@dataclass(slots=True)
class ProbabilityQueryResult:
    """Result of a paid probability query."""

    market: Market
    account: Account
    probability_yes: Decimal
    entropy_fee_charged: Decimal


@dataclass(slots=True)
class AccountTradeResult:
    """Trade result with account and position updates."""

    market: Market
    account: Account
    position: Position
    trade: TradeQuote


@dataclass(slots=True)
class DirectionalLiquidityPosition:
    """Per-account directional LP contribution in one market."""

    lp_id: str
    provider_id: str
    market_id: str
    side: MarketSide
    amount: Decimal
    entered_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class LiquidityProvisionResult:
    """Result of adding one directional LP position from account balance."""

    market: Market
    account: Account
    lp_position: DirectionalLiquidityPosition


@dataclass(slots=True)
class SettlementResult:
    """Settlement result for one account in one market."""

    market: Market
    account: Account
    position: Position
    payout: Decimal


class InMemoryMarketService:
    """Manage market instances and persist state in memory."""

    def __init__(
        self,
        amm_service: DirectionalCpmmService | None = None,
        account_service: InMemoryAccountService | None = None,
        market_index_service: SQLiteMarketIndexService | None = None,
    ) -> None:
        self.amm_service = amm_service or DirectionalCpmmService()
        self.account_service = account_service or InMemoryAccountService()
        self.market_index_service = market_index_service
        self._markets: dict[str, Market] = {}
        self._lp_positions: dict[str, list[DirectionalLiquidityPosition]] = {}
        self._probability_snapshots: dict[str, list[ProbabilitySnapshot]] = {}
        self._lock = Lock()

    def create_market(
        self,
        title: str,
        yes_liquidity,
        no_liquidity,
        description: str | None = None,
        creator_account_id: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        trading_close_at: datetime | None = None,
    ) -> Market:
        """Create and store a new market."""

        now = datetime.now(timezone.utc)
        if not creator_account_id:
            raise ValueError("creator_account_id is required for market creation")
        if trading_close_at is None:
            raise ValueError("trading_close_at is required for market creation")
        normalized_close_at = self._normalize_datetime(trading_close_at, "trading_close_at")
        if normalized_close_at <= now:
            raise ValueError("trading_close_at must be in the future")
        yes_liquidity_decimal = to_decimal(yes_liquidity)
        no_liquidity_decimal = to_decimal(no_liquidity)
        if yes_liquidity_decimal != no_liquidity_decimal:
            raise ValueError("initial YES and NO liquidity must be equal")
        normalized_tags = [tag.strip() for tag in (tags or []) if tag.strip()]
        state = self.amm_service.bootstrap_market(
            yes_liquidity=yes_liquidity_decimal,
            no_liquidity=no_liquidity_decimal,
        )
        self.account_service.debit_usdc(creator_account_id, yes_liquidity_decimal + no_liquidity_decimal)
        market = Market(
            market_id=uuid4().hex,
            title=title,
            description=description,
            creator_account_id=creator_account_id,
            category=category,
            tags=normalized_tags,
            created_at=now,
            trading_close_at=normalized_close_at,
            updated_at=now,
            state=state,
        )
        with self._lock:
            self._markets[market.market_id] = market
            self._lp_positions[market.market_id] = [
                DirectionalLiquidityPosition(
                    lp_id=uuid4().hex,
                    provider_id=creator_account_id,
                    market_id=market.market_id,
                    side=MarketSide.YES,
                    amount=yes_liquidity_decimal,
                    entered_at=now,
                    updated_at=now,
                ),
                DirectionalLiquidityPosition(
                    lp_id=uuid4().hex,
                    provider_id=creator_account_id,
                    market_id=market.market_id,
                    side=MarketSide.NO,
                    amount=no_liquidity_decimal,
                    entered_at=now,
                    updated_at=now,
                ),
            ]
            self._probability_snapshots[market.market_id] = []
            self._record_probability_snapshot_unlocked(market, captured_at=now)
        self._sync_public_market_index(market)
        return market

    def list_markets(self) -> list[Market]:
        """Return all markets sorted by creation time descending."""

        with self._lock:
            for market in self._markets.values():
                self._refresh_market_status_unlocked(market)
            return sorted(
                self._markets.values(),
                key=lambda market: market.created_at,
                reverse=True,
            )

    def get_market(self, market_id: str) -> Market:
        """Return a market or raise if it does not exist."""

        with self._lock:
            market = self._markets.get(market_id)
            if market is None:
                raise KeyError(f"market '{market_id}' not found")
            self._refresh_market_status_unlocked(market)
            return market

    def has_market(self, market_id: str) -> bool:
        """Return whether a runtime market currently exists."""

        with self._lock:
            market = self._markets.get(market_id)
            if market is None:
                return False
            self._refresh_market_status_unlocked(market)
            return True

    def add_liquidity(self, market_id: str, side: MarketSide, amount) -> Market:
        """Apply directional LP capital to a stored market."""

        with self._lock:
            market = self._get_market_unlocked(market_id)
            self._ensure_market_open(market)
            market.state = self.amm_service.add_liquidity(market.state, side, amount)
            market.updated_at = datetime.now(timezone.utc)
            self._record_probability_snapshot_unlocked(market, captured_at=market.updated_at)
            return market

    def add_liquidity_for_account(
        self,
        market_id: str,
        account_id: str,
        side: MarketSide,
        amount,
    ) -> LiquidityProvisionResult:
        """Deduct free USDC and create a directional LP position."""

        liquidity_amount = to_decimal(amount)
        with self._lock:
            market = self._get_market_unlocked(market_id)
            self._ensure_market_open(market)
            account = self.account_service.debit_usdc(account_id, liquidity_amount)
            market.state = self.amm_service.add_liquidity(market.state, side, liquidity_amount)
            now = datetime.now(timezone.utc)
            lp_position = DirectionalLiquidityPosition(
                lp_id=uuid4().hex,
                provider_id=account_id,
                market_id=market_id,
                side=side,
                amount=liquidity_amount,
                entered_at=now,
                updated_at=now,
            )
            self._lp_positions.setdefault(market_id, []).append(lp_position)
            market.updated_at = now
            self._record_probability_snapshot_unlocked(market, captured_at=now)
            return LiquidityProvisionResult(
                market=market,
                account=account,
                lp_position=lp_position,
            )

    def buy_yes(self, market_id: str, share_amount) -> tuple[Market, TradeQuote]:
        """Execute and persist a YES buy trade."""

        return self._apply_trade(market_id, lambda state: self.amm_service.buy_yes(state, share_amount))

    def buy_no(self, market_id: str, share_amount) -> tuple[Market, TradeQuote]:
        """Execute and persist a NO buy trade."""

        return self._apply_trade(market_id, lambda state: self.amm_service.buy_no(state, share_amount))

    def sell_yes(self, market_id: str, share_amount) -> tuple[Market, TradeQuote]:
        """Execute and persist a YES sell trade."""

        return self._apply_trade(market_id, lambda state: self.amm_service.sell_yes(state, share_amount))

    def sell_no(self, market_id: str, share_amount) -> tuple[Market, TradeQuote]:
        """Execute and persist a NO sell trade."""

        return self._apply_trade(market_id, lambda state: self.amm_service.sell_no(state, share_amount))

    def buy_yes_for_account(self, market_id: str, account_id: str, share_amount) -> AccountTradeResult:
        """Execute a YES buy trade and settle against the account ledger."""

        return self._apply_trade_for_account(
            market_id=market_id,
            account_id=account_id,
            share_amount=share_amount,
            side=MarketSide.YES,
            trade_operation=lambda state: self.amm_service.buy_yes(state, share_amount),
            is_buy=True,
        )

    def buy_no_for_account(self, market_id: str, account_id: str, share_amount) -> AccountTradeResult:
        """Execute a NO buy trade and settle against the account ledger."""

        return self._apply_trade_for_account(
            market_id=market_id,
            account_id=account_id,
            share_amount=share_amount,
            side=MarketSide.NO,
            trade_operation=lambda state: self.amm_service.buy_no(state, share_amount),
            is_buy=True,
        )

    def sell_yes_for_account(self, market_id: str, account_id: str, share_amount) -> AccountTradeResult:
        """Execute a YES sell trade and settle against the account ledger."""

        return self._apply_trade_for_account(
            market_id=market_id,
            account_id=account_id,
            share_amount=share_amount,
            side=MarketSide.YES,
            trade_operation=lambda state: self.amm_service.sell_yes(state, share_amount),
            is_buy=False,
        )

    def sell_no_for_account(self, market_id: str, account_id: str, share_amount) -> AccountTradeResult:
        """Execute a NO sell trade and settle against the account ledger."""

        return self._apply_trade_for_account(
            market_id=market_id,
            account_id=account_id,
            share_amount=share_amount,
            side=MarketSide.NO,
            trade_operation=lambda state: self.amm_service.sell_no(state, share_amount),
            is_buy=False,
        )

    def query_probability(self, market_id: str, account_id: str, entropy_fee) -> ProbabilityQueryResult:
        """Charge ENTROPY and return the latest YES probability."""

        with self._lock:
            market = self._get_market_unlocked(market_id)
            self._refresh_market_status_unlocked(market)
            charged_account = self.account_service.debit_entropy(account_id, entropy_fee)
            market.state.collected_information_tax += Decimal(str(entropy_fee))
            market.updated_at = datetime.now(timezone.utc)
            probability_yes = self.amm_service.probability_yes(market.state)
            return ProbabilityQueryResult(
                market=market,
                account=charged_account,
                probability_yes=probability_yes,
                entropy_fee_charged=Decimal(str(entropy_fee)),
            )

    def resolve_market(self, market_id: str, outcome: MarketSide) -> Market:
        """Resolve a market with the final YES or NO outcome."""

        with self._lock:
            market = self._get_market_unlocked(market_id)
            self._refresh_market_status_unlocked(market)
            if market.status == MarketLifecycle.RESOLVED:
                raise ValueError("market already resolved")
            if market.status != MarketLifecycle.CLOSED:
                raise ValueError("market must be closed before resolution")
            market.status = MarketLifecycle.RESOLVED
            market.resolved_outcome = outcome
            market.resolved_at = datetime.now(timezone.utc)
            market.updated_at = market.resolved_at
            self._apply_lp_resolution_unlocked(market)
            self._sync_public_market_index(market)
            return market

    def settle_account(self, market_id: str, account_id: str) -> SettlementResult:
        """Settle one account after a market has been resolved."""

        with self._lock:
            market = self._get_market_unlocked(market_id)
            if market.status != MarketLifecycle.RESOLVED or market.resolved_outcome is None:
                raise ValueError("market is not resolved")
            if account_id in market.settled_accounts:
                raise ValueError("account already settled for this market")
            account, position, payout = self.account_service.settle_position(
                account_id=account_id,
                market_id=market_id,
                winning_side=market.resolved_outcome,
            )
            market.settled_accounts.add(account_id)
            market.updated_at = datetime.now(timezone.utc)
            return SettlementResult(
                market=market,
                account=account,
                position=position,
                payout=payout,
            )

    def _apply_trade(self, market_id: str, trade_operation) -> tuple[Market, TradeQuote]:
        with self._lock:
            market = self._get_market_unlocked(market_id)
            self._ensure_market_open(market)
            quote = trade_operation(market.state)
            market.state = quote.next_state
            market.updated_at = datetime.now(timezone.utc)
            self._record_probability_snapshot_unlocked(market, captured_at=market.updated_at)
            return market, quote

    def _apply_trade_for_account(
        self,
        market_id: str,
        account_id: str,
        share_amount,
        side: MarketSide,
        trade_operation,
        is_buy: bool,
    ) -> AccountTradeResult:
        with self._lock:
            market = self._get_market_unlocked(market_id)
            self._ensure_market_open(market)
            quote = trade_operation(market.state)
            if is_buy:
                account, position = self.account_service.apply_buy(
                    account_id=account_id,
                    market_id=market_id,
                    side=side,
                    share_amount=quote.share_delta,
                    usdc_cost=quote.total_amount,
                )
            else:
                account, position = self.account_service.apply_sell(
                    account_id=account_id,
                    market_id=market_id,
                    side=side,
                    share_amount=quote.share_delta,
                    usdc_credit=quote.total_amount,
                )
            market.state = quote.next_state
            market.updated_at = datetime.now(timezone.utc)
            self._record_probability_snapshot_unlocked(market, captured_at=market.updated_at)
            return AccountTradeResult(
                market=market,
                account=account,
                position=position,
                trade=quote,
            )

    def list_lp_positions(self) -> list[DirectionalLiquidityPosition]:
        """Return all directional LP positions across markets."""

        with self._lock:
            return [
                position
                for market_positions in self._lp_positions.values()
                for position in market_positions
            ]

    def _get_market_unlocked(self, market_id: str) -> Market:
        market = self._markets.get(market_id)
        if market is None:
            raise KeyError(f"market '{market_id}' not found")
        return market

    def _ensure_market_open(self, market: Market) -> None:
        self._refresh_market_status_unlocked(market)
        if market.status != MarketLifecycle.OPEN:
            raise ValueError("market is not open for trading")

    def ensure_market_closed_for_resolution(self, market_id: str) -> Market:
        """Return a market only if its trading window has ended."""

        with self._lock:
            market = self._get_market_unlocked(market_id)
            self._refresh_market_status_unlocked(market)
            if market.status == MarketLifecycle.RESOLVED:
                raise ValueError("market is already resolved")
            if market.status != MarketLifecycle.CLOSED:
                raise ValueError("market must reach trading_close_at before resolution")
            return market

    def _refresh_market_status_unlocked(self, market: Market) -> None:
        if market.status != MarketLifecycle.OPEN:
            return
        now = datetime.now(timezone.utc)
        if now < market.trading_close_at:
            return
        market.status = MarketLifecycle.CLOSED
        market.updated_at = now
        self._sync_public_market_index(market)

    @staticmethod
    def _normalize_datetime(value: datetime, field_name: str) -> datetime:
        if value.tzinfo is None:
            raise ValueError(f"{field_name} must include timezone information")
        return value.astimezone(timezone.utc)

    def _record_probability_snapshot_unlocked(self, market: Market, *, captured_at: datetime) -> None:
        snapshots = self._probability_snapshots.setdefault(market.market_id, [])
        snapshots.append(
            ProbabilitySnapshot(
                captured_at=captured_at,
                probability_yes=self.amm_service.probability_yes(market.state),
            )
        )

    def _apply_lp_resolution_unlocked(self, market: Market) -> None:
        if market.resolved_outcome is None or market.resolved_at is None:
            raise ValueError("market must be resolved before LP allocation")
        lp_positions = self._lp_positions.get(market.market_id, [])
        snapshots = self._probability_snapshots.get(market.market_id, [])
        reward_breakdown = self.amm_service.allocate_information_tax(
            total_tax=market.state.collected_information_tax,
            positions=[
                RewardLPPosition(
                    provider_id=item.provider_id,
                    side=item.side,
                    amount=item.amount,
                    entered_at=item.entered_at,
                )
                for item in lp_positions
            ],
            snapshots=snapshots,
            winning_side=market.resolved_outcome,
            resolved_at=market.resolved_at,
        )
        principal_returns: dict[str, Decimal] = {}
        for position in lp_positions:
            if position.side != market.resolved_outcome:
                continue
            principal_returns[position.provider_id] = principal_returns.get(position.provider_id, ZERO) + position.amount

        for provider_id, principal in principal_returns.items():
            self.account_service.credit_usdc(provider_id, principal)
        for provider_id, reward in reward_breakdown.rewards_by_provider.items():
            if reward <= ZERO:
                continue
            self.account_service.deposit_entropy(provider_id, reward)

        market.lp_principal_returns = principal_returns
        market.lp_fee_rewards = reward_breakdown.rewards_by_provider
        market.agent_reward_pool = reward_breakdown.agent_pool
        market.treasury_reward_pool = reward_breakdown.treasury_pool

    def _sync_public_market_index(self, market: Market) -> None:
        if self.market_index_service is None:
            return
        self.market_index_service.upsert_market(
            market_id=market.market_id,
            title=market.title,
            description=market.description,
            creator_account_id=market.creator_account_id,
            category=market.category,
            tags=market.tags,
            created_at=market.created_at,
            trading_close_at=market.trading_close_at,
            updated_at=market.updated_at,
            status=market.status,
            resolved_outcome=market.resolved_outcome,
            resolved_at=market.resolved_at,
        )
