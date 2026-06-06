"""FastAPI router for delegated session authorization."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from src.auth.dependencies import auth_service, request_auth_service
from src.auth.schemas import (
    CreateSessionRequest,
    RequestSignaturePayloadRequest,
    RequestSignaturePayloadResponse,
    SessionPayloadRequest,
    SessionPayloadResponse,
    SessionResponse,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _to_session_response(session) -> SessionResponse:
    return SessionResponse(
        session_id=session.session_id,
        account_id=session.account_id,
        delegate_id=session.delegate_id,
        allowed_actions=sorted(session.allowed_actions, key=lambda item: item.value),
        remaining_usdc=session.remaining_usdc,
        remaining_entropy=session.remaining_entropy,
        nonce=session.nonce,
        expires_at=session.expires_at,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post(
    "/request-payload",
    name="生成请求签名载荷",
    response_model=RequestSignaturePayloadResponse,
)
def build_request_signature_payload(
    params: RequestSignaturePayloadRequest,
) -> RequestSignaturePayloadResponse:
    """Build the EIP-712 style payload that the wallet should sign for one API request."""

    if params.body is None:
        body_bytes = b""
    else:
        body_bytes = json.dumps(
            params.body,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    try:
        payload = request_auth_service.build_request_payload(
            account_id=params.account_id,
            method=params.method,
            path=params.path,
            body=body_bytes,
            ttl_seconds=params.ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RequestSignaturePayloadResponse(
        typed_data=payload.typed_data,
        nonce=payload.nonce,
        expires_at=payload.expires_at,
        body_hash=payload.body_hash,
    )


@router.post(
    "/session-payload",
    name="生成授权载荷",
    response_model=SessionPayloadResponse,
)
def build_session_payload(params: SessionPayloadRequest) -> SessionPayloadResponse:
    """Build the EIP-712 style payload that the wallet should sign."""

    try:
        payload = auth_service.build_session_payload(
            account_id=params.account_id,
            delegate_id=params.delegate_id,
            allowed_actions=params.allowed_actions,
            max_usdc=params.max_usdc,
            max_entropy=params.max_entropy,
            ttl_seconds=params.ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SessionPayloadResponse(
        typed_data=payload.typed_data,
        nonce=payload.nonce,
        expires_at=payload.expires_at,
    )


@router.post(
    "/sessions",
    name="创建授权会话",
    response_model=SessionResponse,
)
def create_session(params: CreateSessionRequest) -> SessionResponse:
    """Verify a signed payload and store a delegated session."""

    try:
        session = auth_service.create_session(
            account_id=params.account_id,
            delegate_id=params.delegate_id,
            allowed_actions=params.allowed_actions,
            max_usdc=params.max_usdc,
            max_entropy=params.max_entropy,
            nonce=params.nonce,
            expires_at=params.expires_at,
            signature=params.signature,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_session_response(session)


@router.get(
    "/sessions/{session_id}",
    name="会话详情",
    response_model=SessionResponse,
)
def get_session(session_id: str) -> SessionResponse:
    """Return a stored delegated session."""

    try:
        session = auth_service.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_session_response(session)
