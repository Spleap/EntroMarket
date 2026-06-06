"""Tests for Merkle snapshot and proof generation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.amm.market_service import InMemoryMarketService
from src.state.service import StateSnapshotService


def _future_close_at(minutes: int = 10):
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def test_build_snapshot_and_verify_account_proof() -> None:
    market_service = InMemoryMarketService()
    market_service.account_service.deposit_usdc("creator-1", "100000")
    market = market_service.create_market(
        "Demo",
        "100",
        "100",
        creator_account_id="creator-1",
        trading_close_at=_future_close_at(),
    )
    market_service.account_service.deposit_usdc("alice", "20")
    market_service.account_service.deposit_entropy("alice", "3")
    market_service.buy_yes_for_account(market.market_id, "alice", "4")

    snapshot_service = StateSnapshotService(market_service)
    snapshot = snapshot_service.build_snapshot()
    proof = snapshot_service.get_account_proof("alice")

    assert snapshot.leaf_count == 2
    assert {leaf.account_id for leaf in snapshot.leaves} == {"alice", "creator-1"}
    assert proof.account_id == "alice"
    assert proof.merkle_root == snapshot.merkle_root
    assert snapshot_service.verify_proof(proof) is True
