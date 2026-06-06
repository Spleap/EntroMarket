"""EIP-712 style session authorization for delegated market actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from threading import Lock
from uuid import uuid4

from eth_account import Account
from eth_account.messages import encode_typed_data

from src.amm.service import ZERO, to_decimal


class SessionAction(str, Enum):
    """Allowed delegated actions."""

    BUY_YES = "buy_yes"
    BUY_NO = "buy_no"
    SELL_YES = "sell_yes"
    SELL_NO = "sell_no"
    QUERY_PROBABILITY = "query_probability"


@dataclass(slots=True)
class SessionPayload:
    """Unsigned typed data payload plus derived fields."""

    typed_data: dict
    nonce: int
    expires_at: int


@dataclass(slots=True)
class Session:
    """Stored delegated session."""

    session_id: str
    account_id: str
    delegate_id: str
    allowed_actions: set[SessionAction]
    remaining_usdc: Decimal
    remaining_entropy: Decimal
    nonce: int
    expires_at: int
    created_at: datetime
    updated_at: datetime
    signature: str


class InMemorySessionAuthService:
    """Verify EIP-712 session grants and track remaining quotas."""

    DOMAIN_NAME = "EntroMarket Session Authorization"
    DOMAIN_VERSION = "1"
    VERIFYING_CONTRACT = "0x0000000000000000000000000000000000000000"
    CHAIN_ID = 31337

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._next_nonce: dict[str, int] = {}
        self._pending_nonces: dict[str, set[int]] = {}
        self._used_nonces: dict[str, set[int]] = {}
        self._lock = Lock()

    def build_session_payload(
        self,
        account_id: str,
        delegate_id: str,
        allowed_actions: list[SessionAction],
        max_usdc,
        max_entropy,
        ttl_seconds: int,
    ) -> SessionPayload:
        """Issue a new nonce and return the unsigned typed data payload."""

        normalized_account = self._normalize_address(account_id)
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        max_usdc_decimal = self._require_non_negative(max_usdc, "max_usdc")
        max_entropy_decimal = self._require_non_negative(max_entropy, "max_entropy")
        if not allowed_actions:
            raise ValueError("allowed_actions cannot be empty")

        with self._lock:
            nonce = self._next_nonce.get(normalized_account, 0) + 1
            self._next_nonce[normalized_account] = nonce
            self._pending_nonces.setdefault(normalized_account, set()).add(nonce)

        expires_at = int(datetime.now(timezone.utc).timestamp()) + ttl_seconds
        typed_data = self._build_typed_data(
            account_id=normalized_account,
            delegate_id=delegate_id,
            allowed_actions=allowed_actions,
            max_usdc=max_usdc_decimal,
            max_entropy=max_entropy_decimal,
            nonce=nonce,
            expires_at=expires_at,
        )
        return SessionPayload(typed_data=typed_data, nonce=nonce, expires_at=expires_at)

    def create_session(
        self,
        account_id: str,
        delegate_id: str,
        allowed_actions: list[SessionAction],
        max_usdc,
        max_entropy,
        nonce: int,
        expires_at: int,
        signature: str,
    ) -> Session:
        """Verify a signed payload and store a session."""

        normalized_account = self._normalize_address(account_id)
        max_usdc_decimal = self._require_non_negative(max_usdc, "max_usdc")
        max_entropy_decimal = self._require_non_negative(max_entropy, "max_entropy")
        if expires_at <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("session payload already expired")
        typed_data = self._build_typed_data(
            account_id=normalized_account,
            delegate_id=delegate_id,
            allowed_actions=allowed_actions,
            max_usdc=max_usdc_decimal,
            max_entropy=max_entropy_decimal,
            nonce=nonce,
            expires_at=expires_at,
        )
        recovered_account = Account.recover_message(
            encode_typed_data(full_message=typed_data),
            signature=signature,
        )
        if self._normalize_address(recovered_account) != normalized_account:
            raise ValueError("signature does not match account_id")

        with self._lock:
            pending_nonces = self._pending_nonces.get(normalized_account, set())
            used_nonces = self._used_nonces.setdefault(normalized_account, set())
            if nonce not in pending_nonces or nonce in used_nonces:
                raise ValueError("nonce is invalid or already used")
            pending_nonces.remove(nonce)
            used_nonces.add(nonce)
            now = datetime.now(timezone.utc)
            session = Session(
                session_id=uuid4().hex,
                account_id=normalized_account,
                delegate_id=delegate_id,
                allowed_actions=set(allowed_actions),
                remaining_usdc=max_usdc_decimal,
                remaining_entropy=max_entropy_decimal,
                nonce=nonce,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
                signature=signature,
            )
            self._sessions[session.session_id] = session
            return session

    def get_session(self, session_id: str) -> Session:
        """Return a stored session or raise."""

        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"session '{session_id}' not found")
            return session

    def authorize_action(
        self,
        session_id: str,
        action: SessionAction,
        usdc_amount=ZERO,
        entropy_amount=ZERO,
    ) -> Session:
        """Validate action permission and consume the relevant quota."""

        usdc_decimal = self._require_non_negative(usdc_amount, "usdc_amount")
        entropy_decimal = self._require_non_negative(entropy_amount, "entropy_amount")
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"session '{session_id}' not found")
            if session.expires_at <= int(datetime.now(timezone.utc).timestamp()):
                raise ValueError("session expired")
            if action not in session.allowed_actions:
                raise ValueError(f"action '{action.value}' is not allowed for this session")
            if session.remaining_usdc < usdc_decimal:
                raise ValueError("session USDC quota exceeded")
            if session.remaining_entropy < entropy_decimal:
                raise ValueError("session ENTROPY quota exceeded")
            session.remaining_usdc -= usdc_decimal
            session.remaining_entropy -= entropy_decimal
            session.updated_at = datetime.now(timezone.utc)
            return session

    def _build_typed_data(
        self,
        account_id: str,
        delegate_id: str,
        allowed_actions: list[SessionAction],
        max_usdc: Decimal,
        max_entropy: Decimal,
        nonce: int,
        expires_at: int,
    ) -> dict:
        action_mask = self._actions_to_mask(allowed_actions)
        return {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "SessionGrant": [
                    {"name": "account", "type": "address"},
                    {"name": "delegate", "type": "string"},
                    {"name": "actionMask", "type": "uint256"},
                    {"name": "maxUsdc", "type": "string"},
                    {"name": "maxEntropy", "type": "string"},
                    {"name": "nonce", "type": "uint256"},
                    {"name": "expiresAt", "type": "uint256"},
                ],
            },
            "primaryType": "SessionGrant",
            "domain": {
                "name": self.DOMAIN_NAME,
                "version": self.DOMAIN_VERSION,
                "chainId": self.CHAIN_ID,
                "verifyingContract": self.VERIFYING_CONTRACT,
            },
            "message": {
                "account": account_id,
                "delegate": delegate_id,
                "actionMask": action_mask,
                "maxUsdc": str(max_usdc),
                "maxEntropy": str(max_entropy),
                "nonce": nonce,
                "expiresAt": expires_at,
            },
        }

    def _actions_to_mask(self, allowed_actions: list[SessionAction]) -> int:
        mask = 0
        ordered_actions = list(SessionAction)
        for action in allowed_actions:
            mask |= 1 << ordered_actions.index(action)
        return mask

    def _normalize_address(self, address: str) -> str:
        return address.lower()

    def _require_non_negative(self, value, field_name: str) -> Decimal:
        decimal_value = to_decimal(value)
        if decimal_value < ZERO:
            raise ValueError(f"{field_name} must be non-negative")
        return decimal_value
