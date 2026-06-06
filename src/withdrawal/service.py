"""Operator-signed withdrawal intents for external settlement."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from threading import Lock
from uuid import uuid4

from eth_utils import to_checksum_address

from src.amm.account_service import Account, InMemoryAccountService
from src.amm.service import to_decimal
from src.attestation.service import AttestationService, ZERO_ADDRESS


class WithdrawalAsset(str, Enum):
    """Supported withdrawal assets."""

    USDC = "usdc"
    ENTROPY = "entropy"


class WithdrawalStatus(str, Enum):
    """Current withdrawal intent status."""

    SIGNED = "signed"
    EXECUTED = "executed"


@dataclass(slots=True)
class WithdrawalIntent:
    """Stored operator-signed withdrawal intent."""

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
    status: WithdrawalStatus
    created_at: datetime
    operator_address: str
    signature: str
    payload: dict
    executed_tx_hash: str | None = None
    executed_at: datetime | None = None


class WithdrawalService:
    """Create and store signed withdrawal intents."""

    def __init__(
        self,
        account_service: InMemoryAccountService,
        attestation_service: AttestationService,
    ) -> None:
        self.account_service = account_service
        self.attestation_service = attestation_service
        self._withdrawals: dict[str, WithdrawalIntent] = {}
        self._next_nonce: dict[str, int] = {}
        self._lock = Lock()
        self.withdrawal_ttl_seconds = int(os.getenv("WITHDRAWAL_TTL_SECONDS", "1800"))
        self.stable_token_address = self._normalize_address(
            os.getenv("USDNB_TOKEN_ADDRESS")
            or os.getenv("STABLE_TOKEN_ADDRESS")
            or ZERO_ADDRESS
        )
        self.entropy_token_address = self._normalize_address(os.getenv("ENTROPY_TOKEN_ADDRESS") or ZERO_ADDRESS)

    def create_withdrawal(
        self,
        account_id: str,
        destination_address: str,
        asset: WithdrawalAsset,
        amount,
    ) -> tuple[WithdrawalIntent, Account]:
        """Debit internal balance and create a signed withdrawal intent."""

        normalized_account = account_id.lower()
        normalized_destination = destination_address.lower()
        withdrawal_amount = self._require_positive(amount, "amount")
        if not normalized_destination.startswith("0x"):
            raise ValueError("destination_address must be a hex address")

        if asset == WithdrawalAsset.USDC:
            account = self.account_service.debit_usdc(normalized_account, withdrawal_amount)
        else:
            account = self.account_service.withdraw_entropy(normalized_account, withdrawal_amount)

        with self._lock:
            nonce = self._next_nonce.get(normalized_account, 0) + 1
            self._next_nonce[normalized_account] = nonce
            created_at = datetime.now(timezone.utc)
            expiry = int((created_at + timedelta(seconds=self.withdrawal_ttl_seconds)).timestamp())
            withdrawal_id = sha256(
                f"{normalized_account}:{nonce}:{uuid4().hex}".encode("utf-8")
            ).hexdigest()
            asset_address = self._resolve_asset_address(asset)
            amount_units = self._to_token_units(withdrawal_amount)
            payload, signature = self.attestation_service.sign_withdrawal_payload(
                withdrawal_id=withdrawal_id,
                recipient=normalized_destination,
                asset=asset_address,
                amount=amount_units,
                expiry=expiry,
                account_id=normalized_account,
                nonce=nonce,
                created_at=created_at.isoformat(),
            )
            intent = WithdrawalIntent(
                withdrawal_id=withdrawal_id,
                account_id=normalized_account,
                destination_address=normalized_destination,
                asset=asset,
                asset_address=asset_address,
                amount=withdrawal_amount,
                amount_units=amount_units,
                nonce=nonce,
                expiry=expiry,
                vault_address=self.attestation_service.vault_address,
                chain_id=self.attestation_service.chain_id,
                status=WithdrawalStatus.SIGNED,
                created_at=created_at,
                operator_address=payload["operator_address"],
                signature=signature,
                payload=payload,
            )
            self._withdrawals[intent.withdrawal_id] = intent
            return intent, account

    def get_withdrawal(self, withdrawal_id: str) -> WithdrawalIntent:
        """Return one stored withdrawal intent."""

        with self._lock:
            intent = self._withdrawals.get(withdrawal_id)
            if intent is None:
                raise KeyError(f"withdrawal '{withdrawal_id}' not found")
            return intent

    def verify_withdrawal(self, intent: WithdrawalIntent) -> bool:
        """Verify the operator signature over the withdrawal payload."""

        return self.attestation_service.verify_signature(intent.payload, intent.signature)

    def mark_executed(self, withdrawal_id: str, tx_hash: str) -> WithdrawalIntent:
        """Mark one withdrawal as executed on-chain."""

        with self._lock:
            intent = self._withdrawals.get(withdrawal_id)
            if intent is None:
                raise KeyError(f"withdrawal '{withdrawal_id}' not found")
            intent.status = WithdrawalStatus.EXECUTED
            intent.executed_tx_hash = tx_hash
            intent.executed_at = datetime.now(timezone.utc)
            return intent

    def _require_positive(self, value, field_name: str) -> Decimal:
        decimal_value = to_decimal(value)
        if decimal_value <= 0:
            raise ValueError(f"{field_name} must be positive")
        return decimal_value

    def _resolve_asset_address(self, asset: WithdrawalAsset) -> str:
        if asset == WithdrawalAsset.USDC:
            return self.stable_token_address
        return self.entropy_token_address

    def _to_token_units(self, amount: Decimal, decimals: int = 18) -> int:
        scaling_factor = Decimal(10) ** decimals
        scaled_amount = amount * scaling_factor
        if scaled_amount != scaled_amount.to_integral_value():
            raise ValueError("amount has too many decimal places for token units")
        return int(scaled_amount)

    def _normalize_address(self, address: str) -> str:
        return to_checksum_address(address).lower()
