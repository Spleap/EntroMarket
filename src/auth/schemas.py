"""Pydantic schemas for session authorization."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.auth.service import SessionAction


class SessionPayloadRequest(BaseModel):
    account_id: str = Field(..., description="Wallet address authorizing the session")
    delegate_id: str = Field(..., description="Logical delegate identifier for this session")
    allowed_actions: list[SessionAction] = Field(..., description="Allowed delegated actions")
    max_usdc: Decimal = Field(..., description="Maximum USDC spend allowed for the session")
    max_entropy: Decimal = Field(..., description="Maximum ENTROPY spend allowed for the session")
    ttl_seconds: int = Field(..., description="Session payload time-to-live in seconds")


class SessionPayloadResponse(BaseModel):
    typed_data: dict
    nonce: int
    expires_at: int


class RequestSignaturePayloadRequest(BaseModel):
    account_id: str = Field(..., description="Wallet address signing the API request")
    method: str = Field(..., description="HTTP method that will be signed")
    path: str = Field(..., description="Exact request path that will be signed")
    body: dict | list | None = Field(default=None, description="Exact JSON body that will be sent")
    ttl_seconds: int = Field(..., description="Request payload time-to-live in seconds")


class RequestSignaturePayloadResponse(BaseModel):
    typed_data: dict
    nonce: int
    expires_at: int
    body_hash: str


class CreateSessionRequest(BaseModel):
    account_id: str = Field(..., description="Wallet address authorizing the session")
    delegate_id: str = Field(..., description="Logical delegate identifier for this session")
    allowed_actions: list[SessionAction] = Field(..., description="Allowed delegated actions")
    max_usdc: Decimal = Field(..., description="Maximum USDC spend allowed for the session")
    max_entropy: Decimal = Field(..., description="Maximum ENTROPY spend allowed for the session")
    nonce: int = Field(..., description="Server-issued payload nonce")
    expires_at: int = Field(..., description="Payload expiry timestamp")
    signature: str = Field(..., description="Signature over the EIP-712 style payload")


class SessionResponse(BaseModel):
    session_id: str
    account_id: str
    delegate_id: str
    allowed_actions: list[SessionAction]
    remaining_usdc: Decimal
    remaining_entropy: Decimal
    nonce: int
    expires_at: int
    created_at: datetime
    updated_at: datetime
