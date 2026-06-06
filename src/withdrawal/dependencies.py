"""Shared withdrawal service instance."""

from src.amm.router import market_service
from src.attestation.dependencies import attestation_service
from src.withdrawal.service import WithdrawalService

withdrawal_service = WithdrawalService(
    account_service=market_service.account_service,
    attestation_service=attestation_service,
)
