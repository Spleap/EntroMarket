"""Merkle snapshot and proof generation for the in-memory ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256

from src.amm.account_service import Account, Position
from src.amm.market_service import DirectionalLiquidityPosition, InMemoryMarketService


@dataclass(slots=True)
class SnapshotLeaf:
    """Normalized snapshot leaf for one account."""

    account_id: str
    leaf_hash: str
    payload: str
    usdc_balance: Decimal
    entropy_balance: Decimal
    staked_entropy: Decimal
    total_entropy_spent: Decimal
    query_count: int
    positions_hash: str


@dataclass(slots=True)
class StateSnapshot:
    """Snapshot metadata and all account leaves."""

    snapshot_id: str
    created_at: datetime
    merkle_root: str
    leaf_count: int
    leaves: list[SnapshotLeaf]


@dataclass(slots=True)
class AccountProof:
    """Merkle proof for one account leaf."""

    snapshot_id: str
    account_id: str
    merkle_root: str
    leaf_hash: str
    leaf_payload: str
    proof: list[str]
    proof_index: int
    created_at: datetime


class StateSnapshotService:
    """Build deterministic ledger snapshots and Merkle proofs."""

    def __init__(self, market_service: InMemoryMarketService) -> None:
        self.market_service = market_service
        self._latest_snapshot: StateSnapshot | None = None

    def build_snapshot(self) -> StateSnapshot:
        """Build a fresh snapshot from all accounts and positions."""

        accounts = sorted(
            self.market_service.account_service.list_accounts(),
            key=lambda item: item.account_id,
        )
        positions = self.market_service.account_service.list_positions()
        lp_positions = self.market_service.list_lp_positions()
        positions_by_account = self._group_positions_by_account(positions)
        lp_positions_by_account = self._group_lp_positions_by_account(lp_positions)
        leaves: list[SnapshotLeaf] = []
        for account in accounts:
            account_positions = positions_by_account.get(account.account_id, [])
            account_lp_positions = lp_positions_by_account.get(account.account_id, [])
            leaf = self._build_leaf(account, account_positions, account_lp_positions)
            leaves.append(leaf)

        merkle_root = self._build_merkle_root([leaf.leaf_hash for leaf in leaves])
        snapshot = StateSnapshot(
            snapshot_id=sha256(f"{merkle_root}:{len(leaves)}".encode("utf-8")).hexdigest(),
            created_at=datetime.now(timezone.utc),
            merkle_root=merkle_root,
            leaf_count=len(leaves),
            leaves=leaves,
        )
        self._latest_snapshot = snapshot
        return snapshot

    def get_latest_snapshot(self) -> StateSnapshot:
        """Return the latest snapshot or build a new one if missing."""

        if self._latest_snapshot is None:
            return self.build_snapshot()
        return self._latest_snapshot

    def get_account_proof(self, account_id: str) -> AccountProof:
        """Return the proof for one account in the latest snapshot."""

        snapshot = self.get_latest_snapshot()
        leaf_hashes = [leaf.leaf_hash for leaf in snapshot.leaves]
        for index, leaf in enumerate(snapshot.leaves):
            if leaf.account_id == account_id:
                proof = self._build_proof(leaf_hashes, index)
                return AccountProof(
                    snapshot_id=snapshot.snapshot_id,
                    account_id=leaf.account_id,
                    merkle_root=snapshot.merkle_root,
                    leaf_hash=leaf.leaf_hash,
                    leaf_payload=leaf.payload,
                    proof=proof,
                    proof_index=index,
                    created_at=snapshot.created_at,
                )
        raise KeyError(f"account '{account_id}' not found in snapshot")

    def verify_proof(self, proof: AccountProof) -> bool:
        """Verify a proof against the stored root."""

        computed_hash = proof.leaf_hash
        index = proof.proof_index
        for sibling_hash in proof.proof:
            if index % 2 == 0:
                computed_hash = self._hash_pair(computed_hash, sibling_hash)
            else:
                computed_hash = self._hash_pair(sibling_hash, computed_hash)
            index //= 2
        return computed_hash == proof.merkle_root

    def _build_leaf(
        self,
        account: Account,
        positions: list[Position],
        lp_positions: list[DirectionalLiquidityPosition],
    ) -> SnapshotLeaf:
        positions_payload = self._serialize_positions(positions, lp_positions)
        positions_hash = sha256(positions_payload.encode("utf-8")).hexdigest()
        payload = "|".join(
            [
                account.account_id,
                str(account.usdc_balance),
                str(account.entropy_balance),
                str(account.staked_entropy),
                str(account.total_entropy_spent),
                str(account.query_count),
                positions_hash,
            ]
        )
        leaf_hash = sha256(payload.encode("utf-8")).hexdigest()
        return SnapshotLeaf(
            account_id=account.account_id,
            leaf_hash=leaf_hash,
            payload=payload,
            usdc_balance=account.usdc_balance,
            entropy_balance=account.entropy_balance,
            staked_entropy=account.staked_entropy,
            total_entropy_spent=account.total_entropy_spent,
            query_count=account.query_count,
            positions_hash=positions_hash,
        )

    def _serialize_positions(
        self,
        positions: list[Position],
        lp_positions: list[DirectionalLiquidityPosition],
    ) -> str:
        ordered_positions = sorted(positions, key=lambda item: item.market_id)
        ordered_lp_positions = sorted(lp_positions, key=lambda item: (item.market_id, item.entered_at, item.lp_id))
        parts = [f"trade:{position.market_id}:{position.yes_shares}:{position.no_shares}" for position in ordered_positions]
        parts.extend(
            f"lp:{position.market_id}:{position.side.value}:{position.amount}:{position.entered_at.isoformat()}:{position.lp_id}"
            for position in ordered_lp_positions
        )
        return ";".join(parts)

    def _group_positions_by_account(self, positions: list[Position]) -> dict[str, list[Position]]:
        grouped: dict[str, list[Position]] = {}
        for position in positions:
            grouped.setdefault(position.account_id, []).append(position)
        return grouped

    def _group_lp_positions_by_account(
        self,
        positions: list[DirectionalLiquidityPosition],
    ) -> dict[str, list[DirectionalLiquidityPosition]]:
        grouped: dict[str, list[DirectionalLiquidityPosition]] = {}
        for position in positions:
            grouped.setdefault(position.provider_id, []).append(position)
        return grouped

    def _build_merkle_root(self, leaf_hashes: list[str]) -> str:
        if not leaf_hashes:
            return sha256(b"empty").hexdigest()
        level = leaf_hashes[:]
        while len(level) > 1:
            if len(level) % 2 == 1:
                level.append(level[-1])
            next_level: list[str] = []
            for index in range(0, len(level), 2):
                next_level.append(self._hash_pair(level[index], level[index + 1]))
            level = next_level
        return level[0]

    def _build_proof(self, leaf_hashes: list[str], target_index: int) -> list[str]:
        if not leaf_hashes:
            return []
        level = leaf_hashes[:]
        index = target_index
        proof: list[str] = []
        while len(level) > 1:
            if len(level) % 2 == 1:
                level.append(level[-1])
            sibling_index = index + 1 if index % 2 == 0 else index - 1
            proof.append(level[sibling_index])
            next_level: list[str] = []
            for level_index in range(0, len(level), 2):
                next_level.append(self._hash_pair(level[level_index], level[level_index + 1]))
            level = next_level
            index //= 2
        return proof

    def _hash_pair(self, left_hash: str, right_hash: str) -> str:
        return sha256(f"{left_hash}{right_hash}".encode("utf-8")).hexdigest()
