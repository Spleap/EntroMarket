"""Tests for operator-signed withdrawal intents."""

from __future__ import annotations

from pathlib import Path
from decimal import Decimal

from src.amm.market_service import InMemoryMarketService
from src.attestation.service import AttestationService
from src.state.service import StateSnapshotService
from src.withdrawal.service import WithdrawalAsset, WithdrawalService


def test_create_withdrawal_debits_balance_and_signs_payload() -> None:
    market_service = InMemoryMarketService()
    market_service.account_service.deposit_usdc("alice", "25")
    snapshot_service = StateSnapshotService(market_service)
    snapshot_service.build_snapshot()
    attestation_service = AttestationService(
        snapshot_service=snapshot_service,
        project_root=Path(__file__).resolve().parents[1],
    )
    withdrawal_service = WithdrawalService(
        account_service=market_service.account_service,
        attestation_service=attestation_service,
    )

    intent, account = withdrawal_service.create_withdrawal(
        account_id="alice",
        destination_address="0x1111111111111111111111111111111111111111",
        asset=WithdrawalAsset.USDC,
        amount="5",
    )

    assert account.usdc_balance == Decimal("20")
    assert intent.amount == Decimal("5")
    assert intent.asset == WithdrawalAsset.USDC
    assert intent.amount_units == 5 * 10**18
    assert intent.payload["signature_kind"] == "evm_withdrawal"
    assert intent.payload["asset"] == intent.asset_address
    assert intent.payload["vault"] == intent.vault_address
    assert withdrawal_service.verify_withdrawal(intent) is True
