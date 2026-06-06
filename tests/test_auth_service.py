"""Tests for delegated session authorization."""

from __future__ import annotations

from decimal import Decimal

from eth_account import Account
from eth_account.messages import encode_typed_data

from src.auth.service import InMemorySessionAuthService, SessionAction


def test_create_session_and_consume_quota() -> None:
    service = InMemorySessionAuthService()
    signer = Account.create()
    account_id = signer.address.lower()

    payload = service.build_session_payload(
        account_id=account_id,
        delegate_id="web-client",
        allowed_actions=[SessionAction.BUY_YES, SessionAction.QUERY_PROBABILITY],
        max_usdc="10",
        max_entropy="2",
        ttl_seconds=600,
    )
    signed = Account.sign_message(
        encode_typed_data(full_message=payload.typed_data),
        signer.key,
    )
    session = service.create_session(
        account_id=account_id,
        delegate_id="web-client",
        allowed_actions=[SessionAction.BUY_YES, SessionAction.QUERY_PROBABILITY],
        max_usdc="10",
        max_entropy="2",
        nonce=payload.nonce,
        expires_at=payload.expires_at,
        signature=signed.signature.to_0x_hex(),
    )

    service.authorize_action(session.session_id, SessionAction.BUY_YES, usdc_amount="3.5")
    updated_session = service.authorize_action(
        session.session_id,
        SessionAction.QUERY_PROBABILITY,
        entropy_amount="0.5",
    )

    assert updated_session.remaining_usdc == Decimal("6.5")
    assert updated_session.remaining_entropy == Decimal("1.5")
