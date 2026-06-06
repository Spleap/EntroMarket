"""FastAPI router for state snapshots and Merkle proofs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.attestation.dependencies import attestation_service
from src.attestation.schemas import StateRootSignatureResponse
from src.auth.dependencies import require_signed_request
from src.auth.request_service import SignedRequestContext
from src.state.dependencies import snapshot_service
from src.state.schemas import (
    AccountProofBundleResponse,
    AccountProofResponse,
    SnapshotLeafResponse,
    StateSnapshotResponse,
    StateSnapshotSummaryResponse,
)

router = APIRouter(prefix="/state", tags=["State"])


def _to_snapshot_response(snapshot) -> StateSnapshotResponse:
    return StateSnapshotResponse(
        snapshot_id=snapshot.snapshot_id,
        created_at=snapshot.created_at,
        merkle_root=snapshot.merkle_root,
        leaf_count=snapshot.leaf_count,
        leaves=[
            SnapshotLeafResponse(
                account_id=leaf.account_id,
                leaf_hash=leaf.leaf_hash,
                payload=leaf.payload,
                usdc_balance=leaf.usdc_balance,
                entropy_balance=leaf.entropy_balance,
                staked_entropy=leaf.staked_entropy,
                total_entropy_spent=leaf.total_entropy_spent,
                query_count=leaf.query_count,
                positions_hash=leaf.positions_hash,
            )
            for leaf in snapshot.leaves
        ],
    )


def _to_snapshot_summary_response(snapshot) -> StateSnapshotSummaryResponse:
    return StateSnapshotSummaryResponse(
        snapshot_id=snapshot.snapshot_id,
        created_at=snapshot.created_at,
        merkle_root=snapshot.merkle_root,
        leaf_count=snapshot.leaf_count,
    )


def _to_state_root_signature_response(signed_root) -> StateRootSignatureResponse:
    return StateRootSignatureResponse(
        snapshot_id=signed_root.snapshot_id,
        merkle_root=signed_root.merkle_root,
        timestamp=signed_root.timestamp,
        operator_address=signed_root.operator_address,
        vault_address=signed_root.vault_address,
        chain_id=signed_root.chain_id,
        signature=signed_root.signature,
        payload=signed_root.payload,
        signature_valid=attestation_service.verify_signature(signed_root.payload, signed_root.signature),
    )


def _require_account_owner(account_id: str, signed_request: SignedRequestContext) -> None:
    if signed_request.account_id != account_id.lower():
        raise HTTPException(status_code=403, detail="signed account does not match requested account proof")


@router.post(
    "/snapshot",
    name="生成状态快照",
    response_model=StateSnapshotResponse,
)
def create_snapshot() -> StateSnapshotResponse:
    """Build a fresh snapshot and return its Merkle root."""

    snapshot = snapshot_service.build_snapshot()
    return _to_snapshot_response(snapshot)


@router.get(
    "/snapshot/latest",
    name="最新状态快照",
    response_model=StateSnapshotResponse,
)
def get_latest_snapshot() -> StateSnapshotResponse:
    """Return the latest known snapshot."""

    snapshot = snapshot_service.get_latest_snapshot()
    return _to_snapshot_response(snapshot)


@router.get(
    "/proof/{account_id}",
    name="账户状态证明",
    response_model=AccountProofResponse,
)
def get_account_proof(account_id: str) -> AccountProofResponse:
    """Return a Merkle proof for one account in the latest snapshot."""

    try:
        proof = snapshot_service.get_account_proof(account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AccountProofResponse(
        snapshot_id=proof.snapshot_id,
        account_id=proof.account_id,
        merkle_root=proof.merkle_root,
        leaf_hash=proof.leaf_hash,
        leaf_payload=proof.leaf_payload,
        proof=proof.proof,
        proof_index=proof.proof_index,
        created_at=proof.created_at,
        proof_valid=snapshot_service.verify_proof(proof),
    )


@router.get(
    "/proof-bundles/{account_id}",
    name="账户资产证明包",
    response_model=AccountProofBundleResponse,
)
def get_account_proof_bundle(
    account_id: str,
    signed_request: SignedRequestContext = Depends(require_signed_request),
) -> AccountProofBundleResponse:
    """Return one fresh attested proof bundle for a specific account."""

    _require_account_owner(account_id, signed_request)
    snapshot = snapshot_service.build_snapshot()
    try:
        proof = snapshot_service.get_account_proof(account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    signed_root = attestation_service.sign_latest_state_root()
    return AccountProofBundleResponse(
        snapshot=_to_snapshot_summary_response(snapshot),
        proof=AccountProofResponse(
            snapshot_id=proof.snapshot_id,
            account_id=proof.account_id,
            merkle_root=proof.merkle_root,
            leaf_hash=proof.leaf_hash,
            leaf_payload=proof.leaf_payload,
            proof=proof.proof,
            proof_index=proof.proof_index,
            created_at=proof.created_at,
            proof_valid=snapshot_service.verify_proof(proof),
        ),
        state_root_signature=_to_state_root_signature_response(signed_root),
    )
