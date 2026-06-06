"""Pydantic schemas for signed withdrawal intents."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.amm.schemas import AccountResponse
from src.withdrawal.service import WithdrawalAsset


class CreateWithdrawalRequest(BaseModel):
    account_id: str = Field(..., description="Internal account identifier")
    destination_address: str = Field(..., description="Target on-chain address")
    asset: WithdrawalAsset = Field(..., description="Asset to withdraw")
    amount: Decimal = Field(..., description="Amount to withdraw")


class WithdrawalIntentResponse(BaseModel):
    withdrawal_id: str
    account_id: str
    destination_address: str
    asset: WithdrawalAsset
    asset_address: str
    amount: Decimal
    amount_units: int
    nonce: int
    expiry: int
    vault_address: str
    chain_id: int
    status: str
    created_at: datetime
    operator_address: str
    signature: str
    payload: dict
    signature_valid: bool
    executed_tx_hash: str | None = None
    executed_at: datetime | None = None


class CreateWithdrawalResponse(BaseModel):
    account: AccountResponse
    withdrawal: WithdrawalIntentResponse


class ExecuteWithdrawalResponse(BaseModel):
    withdrawal: WithdrawalIntentResponse
    transaction_hash: str
