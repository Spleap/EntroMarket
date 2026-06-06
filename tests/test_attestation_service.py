"""Tests for software attestation and state root signing."""

from __future__ import annotations

from pathlib import Path

from src.amm.market_service import InMemoryMarketService
from src.attestation.service import AttestationService
from src.state.service import StateSnapshotService


def test_attestation_and_state_root_signature_are_verifiable() -> None:
    market_service = InMemoryMarketService()
    market_service.account_service.deposit_usdc("alice", "10")
    snapshot_service = StateSnapshotService(market_service)
    snapshot_service.build_snapshot()
    service = AttestationService(snapshot_service=snapshot_service, project_root=Path(__file__).resolve().parents[1])

    attestation = service.get_attestation()
    state_root_signature = service.sign_latest_state_root()

    assert service.verify_signature(attestation.payload, attestation.signature) is True
    assert service.verify_signature(state_root_signature.payload, state_root_signature.signature) is True
    assert attestation.merkle_root == state_root_signature.merkle_root
    assert state_root_signature.payload["signature_kind"] == "evm_state_root"
    assert state_root_signature.payload["vault"] == state_root_signature.vault_address
    assert state_root_signature.payload["chain_id"] == state_root_signature.chain_id
