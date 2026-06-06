"""FastAPI router for software attestation documents."""

from __future__ import annotations

from fastapi import APIRouter

from src.attestation.dependencies import attestation_service
from src.attestation.schemas import AttestationResponse, StateRootSignatureResponse

router = APIRouter(prefix="/attestation", tags=["Attestation"])


@router.get(
    "",
    name="获取软件证明",
    response_model=AttestationResponse,
)
def get_attestation() -> AttestationResponse:
    """Return the signed attestation document."""

    document = attestation_service.get_attestation()
    return AttestationResponse(
        operator_address=document.operator_address,
        operator_public_key=document.operator_public_key,
        boot_time=document.boot_time,
        code_hash=document.code_hash,
        config_hash=document.config_hash,
        snapshot_id=document.snapshot_id,
        merkle_root=document.merkle_root,
        signature=document.signature,
        payload=document.payload,
        signature_valid=attestation_service.verify_signature(document.payload, document.signature),
    )


@router.get(
    "/state-root-signature",
    name="获取状态根签名",
    response_model=StateRootSignatureResponse,
)
def get_state_root_signature() -> StateRootSignatureResponse:
    """Return the operator signature for the latest state root."""

    signed_root = attestation_service.sign_latest_state_root()
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
