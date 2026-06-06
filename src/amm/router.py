"""FastAPI router for AMM math demos."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from src.amm.account_service import Account, Position
from src.amm.market_service import DirectionalLiquidityPosition, InMemoryMarketService, Market, MarketLifecycle
from src.market_index.service import PublicMarketRecord, SQLiteMarketIndexService
from src.amm.schemas import (
    AddLiquidityRequest,
    AccountLiquidityResponse,
    AccountResponse,
    AccountTradeRequest,
    AccountTradeResponse,
    BootstrapRequest,
    CreateMarketRequest,
    DepositRequest,
    InformationTaxRequest,
    InformationTaxResponse,
    LiquidityPositionResponse,
    MarketResponse,
    MarketStateResponse,
    ProbabilityQueryRequest,
    ProbabilityQueryResponse,
    PositionResponse,
    PublicMarketResponse,
    ResolveMarketRequest,
    SessionProbabilityQueryRequest,
    SessionTradeRequest,
    SettlementResponse,
    StoredAddLiquidityRequest,
    StoredTradeRequest,
    StoredTradeResponse,
    TradeRequest,
    TradeResponse,
)
from src.auth.dependencies import auth_service, require_signed_request
from src.auth.request_service import SignedRequestContext
from src.auth.service import SessionAction
from src.amm.service import (
    DirectionalCpmmService,
    LPPosition,
    MarketState,
    ProbabilitySnapshot,
)

router = APIRouter(prefix="/amm", tags=["AMM"])
service = DirectionalCpmmService()
market_index_service = SQLiteMarketIndexService(
    Path(__file__).resolve().parents[2] / "data" / "market_index.sqlite3"
)
market_service = InMemoryMarketService(service, market_index_service=market_index_service)


def _to_response(state: MarketState) -> MarketStateResponse:
    return MarketStateResponse(
        yes_liquidity=state.yes_liquidity,
        no_liquidity=state.no_liquidity,
        reserve_yes=state.reserve_yes,
        reserve_no=state.reserve_no,
        invariant=state.invariant,
        probability_yes=service.probability_yes(state),
        collected_trading_fee=state.collected_trading_fee,
        collected_collateral=state.collected_collateral,
        collected_information_tax=state.collected_information_tax,
        open_interest_yes=state.open_interest_yes,
        open_interest_no=state.open_interest_no,
    )


def _to_market_response(market: Market) -> MarketResponse:
    return MarketResponse(
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
        state=_to_response(market.state),
    )


def _to_public_market_response(market: PublicMarketRecord) -> PublicMarketResponse:
    return PublicMarketResponse(
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


def _to_state(payload: MarketStateResponse) -> MarketState:
    return MarketState(
        yes_liquidity=payload.yes_liquidity,
        no_liquidity=payload.no_liquidity,
        reserve_yes=payload.reserve_yes,
        reserve_no=payload.reserve_no,
        invariant=payload.invariant,
        collected_trading_fee=payload.collected_trading_fee,
        collected_collateral=payload.collected_collateral,
        collected_information_tax=payload.collected_information_tax,
        open_interest_yes=payload.open_interest_yes,
        open_interest_no=payload.open_interest_no,
    )


def _to_trade_response(result) -> TradeResponse:
    return TradeResponse(
        side=result.side,
        share_delta=result.share_delta,
        base_cost=result.base_cost,
        fee=result.fee,
        total_amount=result.total_amount,
        probability_yes_before=result.probability_yes_before,
        probability_yes_after=result.probability_yes_after,
        next_state=_to_response(result.next_state),
    )


def _to_account_response(account: Account) -> AccountResponse:
    return AccountResponse(
        account_id=account.account_id,
        usdc_balance=account.usdc_balance,
        entropy_balance=account.entropy_balance,
        staked_entropy=account.staked_entropy,
        total_entropy_spent=account.total_entropy_spent,
        query_count=account.query_count,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _to_position_response(position: Position) -> PositionResponse:
    return PositionResponse(
        account_id=position.account_id,
        market_id=position.market_id,
        yes_shares=position.yes_shares,
        no_shares=position.no_shares,
        created_at=position.created_at,
        updated_at=position.updated_at,
    )


def _to_liquidity_position_response(position: DirectionalLiquidityPosition) -> LiquidityPositionResponse:
    return LiquidityPositionResponse(
        lp_id=position.lp_id,
        provider_id=position.provider_id,
        market_id=position.market_id,
        side=position.side,
        amount=position.amount,
        entered_at=position.entered_at,
        updated_at=position.updated_at,
    )


def _get_market_or_404(market_id: str) -> Market:
    try:
        return market_service.get_market(market_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _is_runtime_backed_public_market(market: PublicMarketRecord) -> bool:
    if str(market.status).lower() == MarketLifecycle.RESOLVED:
        return True
    if market_service.has_market(market.market_id):
        return True
    market_index_service.delete_market(market.market_id)
    return False


def _filter_public_markets(markets: list[PublicMarketRecord]) -> list[PublicMarketRecord]:
    return [market for market in markets if _is_runtime_backed_public_market(market)]


def _trade_on_market(trade_fn, market_id: str, share_amount) -> StoredTradeResponse:
    try:
        market, quote = trade_fn(market_id, share_amount)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StoredTradeResponse(market=_to_market_response(market), trade=_to_trade_response(quote))


def _get_account_or_404(account_id: str) -> Account:
    try:
        return market_service.account_service.get_account(account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _trade_on_market_for_account(trade_fn, market_id: str, account_id: str, share_amount) -> AccountTradeResponse:
    try:
        result = trade_fn(market_id, account_id, share_amount)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AccountTradeResponse(
        market=_to_market_response(result.market),
        account=_to_account_response(result.account),
        position=_to_position_response(result.position),
        trade=_to_trade_response(result.trade),
    )


def _provide_liquidity_for_account(
    market_id: str,
    account_id: str,
    side: MarketSide,
    amount,
) -> AccountLiquidityResponse:
    try:
        result = market_service.add_liquidity_for_account(market_id, account_id, side, amount)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AccountLiquidityResponse(
        market=_to_market_response(result.market),
        account=_to_account_response(result.account),
        lp_position=_to_liquidity_position_response(result.lp_position),
    )


def _require_signed_account(account_id: str, signed_request: SignedRequestContext) -> None:
    if signed_request.account_id != account_id.lower():
        raise HTTPException(status_code=403, detail="signed account does not match requested account")


def _authorize_and_trade(
    session_id: str,
    market_id: str,
    share_amount,
    action: SessionAction,
    quote_fn,
    execute_fn,
) -> AccountTradeResponse:
    session = auth_service.get_session(session_id)
    market = _get_market_or_404(market_id)
    quote = quote_fn(market.state, share_amount)
    account = market_service.account_service.get_or_create_account(session.account_id)
    if account.usdc_balance < quote.total_amount:
        raise HTTPException(status_code=400, detail="insufficient USDC balance")
    try:
        auth_service.authorize_action(
            session_id=session_id,
            action=action,
            usdc_amount=quote.total_amount,
        )
        result = execute_fn(market_id, session.account_id, share_amount)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AccountTradeResponse(
        market=_to_market_response(result.market),
        account=_to_account_response(result.account),
        position=_to_position_response(result.position),
        trade=_to_trade_response(result.trade),
    )


@router.post(
    "/bootstrap",
    name="初始化市场",
    response_model=MarketStateResponse,
)
def bootstrap_market(params: BootstrapRequest) -> MarketStateResponse:
    """Bootstrap a new directional CPMM market."""

    state = service.bootstrap_market(
        yes_liquidity=params.yes_liquidity,
        no_liquidity=params.no_liquidity,
    )
    return _to_response(state)


@router.post(
    "/markets",
    name="创建市场",
    response_model=MarketResponse,
)
def create_market(
    params: CreateMarketRequest,
    signed_request: SignedRequestContext = Depends(require_signed_request),
) -> MarketResponse:
    """Create a stored market instance."""

    if params.creator_account_id is None:
        raise HTTPException(status_code=400, detail="creator_account_id is required for market creation")
    _require_signed_account(params.creator_account_id, signed_request)
    try:
        market = market_service.create_market(
            title=params.title,
            description=params.description,
            creator_account_id=params.creator_account_id,
            category=params.category,
            tags=params.tags,
            trading_close_at=params.trading_close_at,
            yes_liquidity=params.yes_liquidity,
            no_liquidity=params.no_liquidity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_market_response(market)


@router.get(
    "/markets",
    name="市场列表",
    response_model=list[PublicMarketResponse],
)
def list_markets(
    q: str | None = Query(default=None, description="Free keyword search over market title and description"),
    status: str | None = Query(default=None, description="Optional market lifecycle filter"),
    category: str | None = Query(default=None, description="Optional public category filter"),
    creator_account_id: str | None = Query(default=None, description="Optional creator account filter"),
    tag: str | None = Query(default=None, description="Optional exact tag filter"),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum number of free search results"),
) -> list[PublicMarketResponse]:
    """List public market metadata without leaking runtime probability state."""

    markets = _filter_public_markets(
        market_index_service.list_markets(
            query=q,
            status=status,
            category=category,
            creator_account_id=creator_account_id,
            tag=tag,
            limit=limit,
        )
    )
    return [_to_public_market_response(item) for item in markets]


@router.get(
    "/markets/search",
    name="命题广场搜索",
    response_model=list[PublicMarketResponse],
)
def search_markets(
    q: str | None = Query(default=None, description="Keyword search over title and description"),
    status: str | None = Query(default=None, description="Optional market lifecycle filter"),
    category: str | None = Query(default=None, description="Optional public category filter"),
    creator_account_id: str | None = Query(default=None, description="Optional creator account filter"),
    tag: str | None = Query(default=None, description="Optional exact tag filter"),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum number of free search results"),
) -> list[PublicMarketResponse]:
    """Alias for front-end friendly public market search."""

    return list_markets(
        q=q,
        status=status,
        category=category,
        creator_account_id=creator_account_id,
        tag=tag,
        limit=limit,
    )


@router.get(
    "/markets/{market_id}",
    name="市场详情",
    response_model=PublicMarketResponse,
)
def get_market(market_id: str) -> PublicMarketResponse:
    """Get free public market metadata without runtime state."""

    try:
        market = market_index_service.get_market(market_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not _is_runtime_backed_public_market(market):
        raise HTTPException(status_code=404, detail=f"market '{market_id}' not found")
    return _to_public_market_response(market)


@router.get(
    "/accounts/{account_id}",
    name="账户详情",
    response_model=AccountResponse,
)
def get_account(account_id: str) -> AccountResponse:
    """Get an internal ledger account by id."""

    return _to_account_response(_get_account_or_404(account_id))


@router.post(
    "/accounts/{account_id}/deposit-usdc",
    name="充值USDC到账本",
    response_model=AccountResponse,
)
def deposit_usdc(
    account_id: str,
    params: DepositRequest,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> AccountResponse:
    """Credit the internal USDC balance."""

    account = market_service.account_service.deposit_usdc(account_id, params.amount)
    return _to_account_response(account)


@router.post(
    "/accounts/{account_id}/deposit-entropy",
    name="充值ENTROPY到账本",
    response_model=AccountResponse,
)
def deposit_entropy(
    account_id: str,
    params: DepositRequest,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> AccountResponse:
    """Credit the internal ENTROPY balance."""

    account = market_service.account_service.deposit_entropy(account_id, params.amount)
    return _to_account_response(account)


@router.get(
    "/accounts/{account_id}/markets/{market_id}/position",
    name="账户市场持仓",
    response_model=PositionResponse,
)
def get_position(account_id: str, market_id: str) -> PositionResponse:
    """Get an account position for a specific market."""

    position = market_service.account_service.get_position(account_id, market_id)
    return _to_position_response(position)


@router.post(
    "/add-liquidity",
    name="添加方向性流动性",
    response_model=MarketStateResponse,
)
def add_liquidity(params: AddLiquidityRequest) -> MarketStateResponse:
    """Apply one-sided LP capital to the market state."""

    next_state = service.add_liquidity(_to_state(params.state), params.side, params.amount)
    return _to_response(next_state)


@router.post(
    "/markets/{market_id}/add-liquidity",
    name="向市场添加方向性流动性",
    response_model=MarketResponse,
)
def add_liquidity_to_market(market_id: str, params: StoredAddLiquidityRequest) -> MarketResponse:
    """Apply one-sided LP capital to a stored market."""

    try:
        market = market_service.add_liquidity(market_id, params.side, params.amount)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_market_response(market)


@router.post(
    "/markets/{market_id}/accounts/{account_id}/add-liquidity",
    name="账户添加方向性流动性",
    response_model=AccountLiquidityResponse,
)
def add_liquidity_to_market_for_account(
    market_id: str,
    account_id: str,
    params: StoredAddLiquidityRequest,
    signed_request: SignedRequestContext = Depends(require_signed_request),
) -> AccountLiquidityResponse:
    """Use free internal USDC balance to become a directional LP."""

    _require_signed_account(account_id, signed_request)
    return _provide_liquidity_for_account(
        market_id=market_id,
        account_id=account_id,
        side=params.side,
        amount=params.amount,
    )


@router.post(
    "/buy-yes",
    name="买入YES",
    response_model=TradeResponse,
)
def buy_yes(params: TradeRequest) -> TradeResponse:
    """Execute a YES buy trade."""

    return _to_trade_response(service.buy_yes(_to_state(params.state), params.share_amount))


@router.post(
    "/markets/{market_id}/buy-yes",
    name="市场买入YES",
    response_model=StoredTradeResponse,
)
def buy_yes_on_market(market_id: str, params: StoredTradeRequest) -> StoredTradeResponse:
    """Execute a YES buy trade on a stored market."""

    return _trade_on_market(market_service.buy_yes, market_id, params.share_amount)


@router.post(
    "/markets/{market_id}/accounts/{account_id}/buy-yes",
    name="账户买入YES",
    response_model=AccountTradeResponse,
)
def buy_yes_on_market_for_account(
    market_id: str,
    account_id: str,
    params: AccountTradeRequest,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> AccountTradeResponse:
    """Execute a YES buy trade against the internal account ledger."""

    return _trade_on_market_for_account(
        market_service.buy_yes_for_account,
        market_id,
        account_id,
        params.share_amount,
    )


@router.post(
    "/markets/{market_id}/session/buy-yes",
    name="会话买入YES",
    response_model=AccountTradeResponse,
)
def buy_yes_with_session(market_id: str, params: SessionTradeRequest) -> AccountTradeResponse:
    """Execute a YES buy trade using a delegated session."""

    return _authorize_and_trade(
        session_id=params.session_id,
        market_id=market_id,
        share_amount=params.share_amount,
        action=SessionAction.BUY_YES,
        quote_fn=service.buy_yes,
        execute_fn=market_service.buy_yes_for_account,
    )


@router.post(
    "/buy-no",
    name="买入NO",
    response_model=TradeResponse,
)
def buy_no(params: TradeRequest) -> TradeResponse:
    """Execute a NO buy trade."""

    return _to_trade_response(service.buy_no(_to_state(params.state), params.share_amount))


@router.post(
    "/markets/{market_id}/buy-no",
    name="市场买入NO",
    response_model=StoredTradeResponse,
)
def buy_no_on_market(market_id: str, params: StoredTradeRequest) -> StoredTradeResponse:
    """Execute a NO buy trade on a stored market."""

    return _trade_on_market(market_service.buy_no, market_id, params.share_amount)


@router.post(
    "/markets/{market_id}/accounts/{account_id}/buy-no",
    name="账户买入NO",
    response_model=AccountTradeResponse,
)
def buy_no_on_market_for_account(
    market_id: str,
    account_id: str,
    params: AccountTradeRequest,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> AccountTradeResponse:
    """Execute a NO buy trade against the internal account ledger."""

    return _trade_on_market_for_account(
        market_service.buy_no_for_account,
        market_id,
        account_id,
        params.share_amount,
    )


@router.post(
    "/markets/{market_id}/session/buy-no",
    name="会话买入NO",
    response_model=AccountTradeResponse,
)
def buy_no_with_session(market_id: str, params: SessionTradeRequest) -> AccountTradeResponse:
    """Execute a NO buy trade using a delegated session."""

    return _authorize_and_trade(
        session_id=params.session_id,
        market_id=market_id,
        share_amount=params.share_amount,
        action=SessionAction.BUY_NO,
        quote_fn=service.buy_no,
        execute_fn=market_service.buy_no_for_account,
    )


@router.post(
    "/sell-yes",
    name="卖出YES",
    response_model=TradeResponse,
)
def sell_yes(params: TradeRequest) -> TradeResponse:
    """Execute a YES sell trade."""

    return _to_trade_response(service.sell_yes(_to_state(params.state), params.share_amount))


@router.post(
    "/markets/{market_id}/sell-yes",
    name="市场卖出YES",
    response_model=StoredTradeResponse,
)
def sell_yes_on_market(market_id: str, params: StoredTradeRequest) -> StoredTradeResponse:
    """Execute a YES sell trade on a stored market."""

    return _trade_on_market(market_service.sell_yes, market_id, params.share_amount)


@router.post(
    "/markets/{market_id}/accounts/{account_id}/sell-yes",
    name="账户卖出YES",
    response_model=AccountTradeResponse,
)
def sell_yes_on_market_for_account(
    market_id: str,
    account_id: str,
    params: AccountTradeRequest,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> AccountTradeResponse:
    """Execute a YES sell trade against the internal account ledger."""

    return _trade_on_market_for_account(
        market_service.sell_yes_for_account,
        market_id,
        account_id,
        params.share_amount,
    )


@router.post(
    "/markets/{market_id}/session/sell-yes",
    name="会话卖出YES",
    response_model=AccountTradeResponse,
)
def sell_yes_with_session(market_id: str, params: SessionTradeRequest) -> AccountTradeResponse:
    """Execute a YES sell trade using a delegated session."""

    return _authorize_and_trade(
        session_id=params.session_id,
        market_id=market_id,
        share_amount=params.share_amount,
        action=SessionAction.SELL_YES,
        quote_fn=service.sell_yes,
        execute_fn=market_service.sell_yes_for_account,
    )


@router.post(
    "/sell-no",
    name="卖出NO",
    response_model=TradeResponse,
)
def sell_no(params: TradeRequest) -> TradeResponse:
    """Execute a NO sell trade."""

    return _to_trade_response(service.sell_no(_to_state(params.state), params.share_amount))


@router.post(
    "/markets/{market_id}/sell-no",
    name="市场卖出NO",
    response_model=StoredTradeResponse,
)
def sell_no_on_market(market_id: str, params: StoredTradeRequest) -> StoredTradeResponse:
    """Execute a NO sell trade on a stored market."""

    return _trade_on_market(market_service.sell_no, market_id, params.share_amount)


@router.post(
    "/markets/{market_id}/accounts/{account_id}/sell-no",
    name="账户卖出NO",
    response_model=AccountTradeResponse,
)
def sell_no_on_market_for_account(
    market_id: str,
    account_id: str,
    params: AccountTradeRequest,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> AccountTradeResponse:
    """Execute a NO sell trade against the internal account ledger."""

    return _trade_on_market_for_account(
        market_service.sell_no_for_account,
        market_id,
        account_id,
        params.share_amount,
    )


@router.post(
    "/markets/{market_id}/session/sell-no",
    name="会话卖出NO",
    response_model=AccountTradeResponse,
)
def sell_no_with_session(market_id: str, params: SessionTradeRequest) -> AccountTradeResponse:
    """Execute a NO sell trade using a delegated session."""

    return _authorize_and_trade(
        session_id=params.session_id,
        market_id=market_id,
        share_amount=params.share_amount,
        action=SessionAction.SELL_NO,
        quote_fn=service.sell_no,
        execute_fn=market_service.sell_no_for_account,
    )


@router.post(
    "/markets/{market_id}/query-probability",
    name="付费查询实时概率",
    response_model=ProbabilityQueryResponse,
)
def query_probability(
    market_id: str,
    params: ProbabilityQueryRequest,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> ProbabilityQueryResponse:
    """Charge ENTROPY and return the market probability."""

    try:
        result = market_service.query_probability(
            market_id=market_id,
            account_id=params.account_id,
            entropy_fee=params.entropy_fee,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProbabilityQueryResponse(
        market=_to_market_response(result.market),
        account=_to_account_response(result.account),
        probability_yes=result.probability_yes,
        entropy_fee_charged=result.entropy_fee_charged,
    )


@router.post(
    "/markets/{market_id}/session/query-probability",
    name="会话付费查询实时概率",
    response_model=ProbabilityQueryResponse,
)
def query_probability_with_session(
    market_id: str,
    params: SessionProbabilityQueryRequest,
) -> ProbabilityQueryResponse:
    """Charge ENTROPY and return market probability using a delegated session."""

    try:
        session = auth_service.get_session(params.session_id)
        auth_service.authorize_action(
            session_id=params.session_id,
            action=SessionAction.QUERY_PROBABILITY,
            entropy_amount=params.entropy_fee,
        )
        result = market_service.query_probability(
            market_id=market_id,
            account_id=session.account_id,
            entropy_fee=params.entropy_fee,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProbabilityQueryResponse(
        market=_to_market_response(result.market),
        account=_to_account_response(result.account),
        probability_yes=result.probability_yes,
        entropy_fee_charged=result.entropy_fee_charged,
    )


@router.post(
    "/markets/{market_id}/resolve",
    name="裁决市场结果",
    response_model=MarketResponse,
)
def resolve_market(
    market_id: str,
    params: ResolveMarketRequest,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> MarketResponse:
    """Resolve a market with the final outcome."""

    try:
        market = market_service.resolve_market(market_id, params.outcome)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_market_response(market)


@router.post(
    "/markets/{market_id}/accounts/{account_id}/settle",
    name="结算账户持仓",
    response_model=SettlementResponse,
)
def settle_account(
    market_id: str,
    account_id: str,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> SettlementResponse:
    """Settle one account after the market has been resolved."""

    try:
        result = market_service.settle_account(market_id, account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SettlementResponse(
        market=_to_market_response(result.market),
        account=_to_account_response(result.account),
        position=_to_position_response(result.position),
        payout=result.payout,
    )


@router.post(
    "/information-tax",
    name="分配信息税",
    response_model=InformationTaxResponse,
)
def allocate_information_tax(params: InformationTaxRequest) -> InformationTaxResponse:
    """Allocate information tax to LPs after market resolution."""

    result = service.allocate_information_tax(
        total_tax=params.total_tax,
        positions=[
            LPPosition(
                provider_id=item.provider_id,
                side=item.side,
                amount=item.amount,
                entered_at=item.entered_at,
            )
            for item in params.positions
        ],
        snapshots=[
            ProbabilitySnapshot(
                captured_at=item.captured_at,
                probability_yes=item.probability_yes,
            )
            for item in params.snapshots
        ],
        winning_side=params.winning_side,
        resolved_at=params.resolved_at,
    )
    return InformationTaxResponse(
        winner_pool=result.winner_pool,
        agent_pool=result.agent_pool,
        treasury_pool=result.treasury_pool,
        rewards_by_provider=result.rewards_by_provider,
    )
