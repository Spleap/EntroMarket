"""Per-request EIP-712 style API signature verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from threading import Lock

from eth_account import Account
from eth_account.messages import encode_typed_data


@dataclass(slots=True)
class RequestSignaturePayload:
    """Unsigned typed data payload for one API request."""

    typed_data: dict
    nonce: int
    expires_at: int
    body_hash: str


@dataclass(slots=True)
class SignedRequestContext:
    """Verified request signature context."""

    account_id: str
    method: str
    path: str
    body_hash: str
    nonce: int
    expires_at: int
    signature: str


class RequestSignatureService:
    """Issue and verify one-time signed API request payloads."""

    DOMAIN_NAME = "EntroMarket API Request"
    DOMAIN_VERSION = "1"
    VERIFYING_CONTRACT = "0x0000000000000000000000000000000000000000"
    CHAIN_ID = 31337

    def __init__(self) -> None:
        self._next_nonce: dict[str, int] = {}
        self._pending_nonces: dict[str, set[int]] = {}
        self._used_nonces: dict[str, set[int]] = {}
        self._lock = Lock()

    def build_request_payload(
        self,
        *,
        account_id: str,
        method: str,
        path: str,
        body: bytes,
        ttl_seconds: int,
    ) -> RequestSignaturePayload:
        """Return a server-issued typed data payload for one API request."""

        normalized_account = self._normalize_account(account_id)
        normalized_method = self._normalize_method(method)
        normalized_path = self._normalize_path(path)
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        with self._lock:
            nonce = self._next_nonce.get(normalized_account, 0) + 1
            self._next_nonce[normalized_account] = nonce
            self._pending_nonces.setdefault(normalized_account, set()).add(nonce)

        expires_at = int(datetime.now(timezone.utc).timestamp()) + ttl_seconds
        body_hash = self._hash_body(body)
        typed_data = self._build_typed_data(
            account_id=normalized_account,
            method=normalized_method,
            path=normalized_path,
            body_hash=body_hash,
            nonce=nonce,
            expires_at=expires_at,
        )
        return RequestSignaturePayload(
            typed_data=typed_data,
            nonce=nonce,
            expires_at=expires_at,
            body_hash=body_hash,
        )

    def authorize_request(
        self,
        *,
        account_id: str,
        method: str,
        path: str,
        body: bytes,
        nonce: int,
        expires_at: int,
        signature: str,
    ) -> SignedRequestContext:
        """Verify one signed API request and consume its nonce."""

        normalized_account = self._normalize_account(account_id)
        normalized_method = self._normalize_method(method)
        normalized_path = self._normalize_path(path)
        if expires_at <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("request signature expired")
        body_hash = self._hash_body(body)
        typed_data = self._build_typed_data(
            account_id=normalized_account,
            method=normalized_method,
            path=normalized_path,
            body_hash=body_hash,
            nonce=nonce,
            expires_at=expires_at,
        )
        recovered_account = Account.recover_message(
            encode_typed_data(full_message=typed_data),
            signature=signature,
        )
        if self._normalize_account(recovered_account) != normalized_account:
            raise ValueError("signature does not match account_id")

        with self._lock:
            pending_nonces = self._pending_nonces.get(normalized_account, set())
            used_nonces = self._used_nonces.setdefault(normalized_account, set())
            if nonce not in pending_nonces or nonce in used_nonces:
                raise ValueError("nonce is invalid or already used")
            pending_nonces.remove(nonce)
            used_nonces.add(nonce)

        return SignedRequestContext(
            account_id=normalized_account,
            method=normalized_method,
            path=normalized_path,
            body_hash=body_hash,
            nonce=nonce,
            expires_at=expires_at,
            signature=signature,
        )

    def _build_typed_data(
        self,
        *,
        account_id: str,
        method: str,
        path: str,
        body_hash: str,
        nonce: int,
        expires_at: int,
    ) -> dict:
        return {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "ApiRequest": [
                    {"name": "account", "type": "address"},
                    {"name": "method", "type": "string"},
                    {"name": "path", "type": "string"},
                    {"name": "bodyHash", "type": "string"},
                    {"name": "nonce", "type": "uint256"},
                    {"name": "expiresAt", "type": "uint256"},
                ],
            },
            "primaryType": "ApiRequest",
            "domain": {
                "name": self.DOMAIN_NAME,
                "version": self.DOMAIN_VERSION,
                "chainId": self.CHAIN_ID,
                "verifyingContract": self.VERIFYING_CONTRACT,
            },
            "message": {
                "account": account_id,
                "method": method,
                "path": path,
                "bodyHash": body_hash,
                "nonce": nonce,
                "expiresAt": expires_at,
            },
        }

    def _normalize_account(self, account_id: str) -> str:
        return account_id.lower()

    def _normalize_method(self, method: str) -> str:
        if not method:
            raise ValueError("method cannot be empty")
        return method.upper()

    def _normalize_path(self, path: str) -> str:
        if not path.startswith("/"):
            raise ValueError("path must start with '/'")
        return path

    def _hash_body(self, body: bytes) -> str:
        return f"0x{sha256(body).hexdigest()}"
