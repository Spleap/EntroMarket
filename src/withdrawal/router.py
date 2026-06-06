"""FastAPI router for operator-signed withdrawal intents."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.amm.router import _to_account_response
from src.auth.dependencies import require_signed_request
from src.auth.request_service import SignedRequestContext
from src.withdrawal.dependencies import withdrawal_service
from src.withdrawal.schemas import (
    CreateWithdrawalRequest,
    CreateWithdrawalResponse,
    WithdrawalIntentResponse,
)

router = APIRouter(prefix="/withdrawals", tags=["Withdrawals"])


def _to_withdrawal_response(intent) -> WithdrawalIntentResponse:
    return WithdrawalIntentResponse(
        withdrawal_id=intent.withdrawal_id,
        account_id=intent.account_id,
        destination_address=intent.destination_address,
        asset=intent.asset,
        asset_address=intent.asset_address,
        amount=intent.amount,
        amount_units=intent.amount_units,
        nonce=intent.nonce,
        expiry=intent.expiry,
        vault_address=intent.vault_address,
        chain_id=intent.chain_id,
        status=intent.status.value,
        created_at=intent.created_at,
        operator_address=intent.operator_address,
        signature=intent.signature,
        payload=intent.payload,
        signature_valid=withdrawal_service.verify_withdrawal(intent),
        executed_tx_hash=intent.executed_tx_hash,
        executed_at=intent.executed_at,
    )


@router.post(
    "",
    name="创建提现意图",
    response_model=CreateWithdrawalResponse,
)
def create_withdrawal(
    params: CreateWithdrawalRequest,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> CreateWithdrawalResponse:
    """Create an operator-signed withdrawal intent."""

    try:
        intent, account = withdrawal_service.create_withdrawal(
            account_id=params.account_id,
            destination_address=params.destination_address,
            asset=params.asset,
            amount=params.amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CreateWithdrawalResponse(
        account=_to_account_response(account),
        withdrawal=_to_withdrawal_response(intent),
    )


@router.get(
    "/{withdrawal_id}",
    name="提现意图详情",
    response_model=WithdrawalIntentResponse,
)
def get_withdrawal(withdrawal_id: str) -> WithdrawalIntentResponse:
    """Return one stored withdrawal intent."""

    try:
        intent = withdrawal_service.get_withdrawal(withdrawal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_withdrawal_response(intent)
