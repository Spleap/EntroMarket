"""Shared auth service instances and signature dependencies."""

from __future__ import annotations

from fastapi import HTTPException, Request

from src.auth.request_service import RequestSignatureService, SignedRequestContext
from src.auth.service import InMemorySessionAuthService

auth_service = InMemorySessionAuthService()
request_auth_service = RequestSignatureService()


async def require_signed_request(request: Request) -> SignedRequestContext:
    """Verify per-request signature headers for sensitive endpoints."""

    account_id = request.headers.get("x-entro-account")
    nonce = request.headers.get("x-entro-nonce")
    expires_at = request.headers.get("x-entro-expires-at")
    signature = request.headers.get("x-entro-signature")
    if not account_id or not nonce or not expires_at or not signature:
        raise HTTPException(status_code=401, detail="missing signed request headers")
    try:
        return request_auth_service.authorize_request(
            account_id=account_id,
            method=request.method,
            path=request.url.path,
            body=await request.body(),
            nonce=int(nonce),
            expires_at=int(expires_at),
            signature=signature,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
