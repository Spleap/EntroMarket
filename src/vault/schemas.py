"""Schemas for real vault deposit sync and withdrawal relay."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.amm.schemas import AccountResponse
from src.attestation.schemas import StateRootSignatureResponse
from src.withdrawal.schemas import WithdrawalIntentResponse
from src.withdrawal.service import WithdrawalAsset


class SyncDepositRequest(BaseModel):
    account_id: str = Field(..., description="Internal account id, typically the depositor wallet address")
    asset: WithdrawalAsset = Field(..., description="Asset deposited into the vault")
    transaction_hash: str = Field(..., description="On-chain deposit transaction hash")


class SyncDepositResponse(BaseModel):
    account: AccountResponse
    account_id: str
    depositor_address: str
    asset: WithdrawalAsset
    amount: Decimal
    amount_units: int
    transaction_hash: str
    block_number: int
    synced_at: datetime


class ExecuteVaultWithdrawalResponse(BaseModel):
    withdrawal: WithdrawalIntentResponse
    transaction_hash: str
    block_number: int
    executed_at: datetime


class SubmitStateRootResponse(BaseModel):
    state_root_signature: StateRootSignatureResponse
    transaction_hash: str
    block_number: int
    submitted_at: datetime
