"""FastAPI router for real vault deposit sync and withdrawal execution."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.amm.router import _to_account_response
from src.attestation.schemas import StateRootSignatureResponse
from src.auth.dependencies import require_signed_request
from src.auth.request_service import SignedRequestContext
from src.withdrawal.router import _to_withdrawal_response
from src.vault.dependencies import vault_service
from src.vault.schemas import (
    ExecuteVaultWithdrawalResponse,
    SubmitStateRootResponse,
    SyncDepositRequest,
    SyncDepositResponse,
)

router = APIRouter(prefix="/vault", tags=["Vault"])


def _to_state_root_signature_response(result) -> StateRootSignatureResponse:
    return StateRootSignatureResponse(
        snapshot_id=result.snapshot_id,
        merkle_root=result.merkle_root,
        timestamp=result.timestamp,
        operator_address=result.operator_address,
        vault_address=result.vault_address,
        chain_id=result.chain_id,
        signature=result.signature,
        payload=result.payload,
        signature_valid=True,
    )


def _require_relayer_account(signed_request: SignedRequestContext) -> None:
    relayer_address = vault_service.get_relayer_address()
    if relayer_address is None:
        raise HTTPException(status_code=400, detail="PRIVATE_KEY is not configured for state root submission")
    if signed_request.account_id != relayer_address:
        raise HTTPException(status_code=403, detail="signed account is not authorized to submit state roots")


@router.post(
    "/deposits/sync",
    name="同步链上充值到账本",
    response_model=SyncDepositResponse,
)
def sync_deposit(
    params: SyncDepositRequest,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> SyncDepositResponse:
    """Read one on-chain vault deposit and credit the internal ledger."""

    try:
        result = vault_service.sync_deposit(
            account_id=params.account_id,
            asset=params.asset,
            transaction_hash=params.transaction_hash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SyncDepositResponse(
        account=_to_account_response(result.account),
        account_id=result.account_id,
        depositor_address=result.depositor_address,
        asset=result.asset,
        amount=result.amount,
        amount_units=result.amount_units,
        transaction_hash=result.transaction_hash,
        block_number=result.block_number,
        synced_at=result.synced_at,
    )


@router.post(
    "/withdrawals/{withdrawal_id}/execute",
    name="执行链上提现",
    response_model=ExecuteVaultWithdrawalResponse,
)
def execute_withdrawal(
    withdrawal_id: str,
    _signed_request: SignedRequestContext = Depends(require_signed_request),
) -> ExecuteVaultWithdrawalResponse:
    """Broadcast one stored operator-signed withdrawal to the configured vault."""

    try:
        result = vault_service.execute_withdrawal(withdrawal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExecuteVaultWithdrawalResponse(
        withdrawal=_to_withdrawal_response(result.withdrawal),
        transaction_hash=result.transaction_hash,
        block_number=result.block_number,
        executed_at=result.executed_at,
    )


@router.post(
    "/state-root/submit",
    name="提交最新状态根到链上",
    response_model=SubmitStateRootResponse,
)
def submit_state_root(
    signed_request: SignedRequestContext = Depends(require_signed_request),
) -> SubmitStateRootResponse:
    """Submit the latest signed state root to the configured vault."""

    _require_relayer_account(signed_request)
    try:
        result = vault_service.submit_latest_state_root()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SubmitStateRootResponse(
        state_root_signature=_to_state_root_signature_response(result),
        transaction_hash=result.transaction_hash,
        block_number=result.block_number,
        submitted_at=result.submitted_at,
    )
