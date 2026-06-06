"""Pydantic schemas for software attestation and root signatures."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AttestationResponse(BaseModel):
    operator_address: str
    operator_public_key: str
    boot_time: datetime
    code_hash: str
    config_hash: str
    snapshot_id: str
    merkle_root: str
    signature: str
    payload: dict
    signature_valid: bool


class StateRootSignatureResponse(BaseModel):
    snapshot_id: str
    merkle_root: str
    timestamp: datetime
    operator_address: str
    vault_address: str
    chain_id: int
    signature: str
    payload: dict
    signature_valid: bool
