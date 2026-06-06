"""Pydantic schemas for ledger snapshots and proofs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from src.attestation.schemas import StateRootSignatureResponse


class SnapshotLeafResponse(BaseModel):
    account_id: str
    leaf_hash: str
    payload: str
    usdc_balance: Decimal
    entropy_balance: Decimal
    staked_entropy: Decimal
    total_entropy_spent: Decimal
    query_count: int
    positions_hash: str


class StateSnapshotResponse(BaseModel):
    snapshot_id: str
    created_at: datetime
    merkle_root: str
    leaf_count: int
    leaves: list[SnapshotLeafResponse]


class StateSnapshotSummaryResponse(BaseModel):
    snapshot_id: str
    created_at: datetime
    merkle_root: str
    leaf_count: int


class AccountProofResponse(BaseModel):
    snapshot_id: str
    account_id: str
    merkle_root: str
    leaf_hash: str
    leaf_payload: str
    proof: list[str]
    proof_index: int
    created_at: datetime
    proof_valid: bool


class AccountProofBundleResponse(BaseModel):
    snapshot: StateSnapshotSummaryResponse
    proof: AccountProofResponse
    state_root_signature: StateRootSignatureResponse
