"""Shared vault service instance."""

from src.amm.router import market_service
from src.attestation.dependencies import attestation_service
from src.withdrawal.dependencies import withdrawal_service
from src.vault.service import VaultService

vault_service = VaultService(
    account_service=market_service.account_service,
    withdrawal_service=withdrawal_service,
    attestation_service=attestation_service,
)
