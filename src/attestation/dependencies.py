"""Shared attestation service instance."""

from pathlib import Path

from src.attestation.service import AttestationService
from src.state.dependencies import snapshot_service

attestation_service = AttestationService(
    snapshot_service=snapshot_service,
    project_root=Path(__file__).resolve().parents[2],
)
