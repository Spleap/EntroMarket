"""Shared governance service instance."""

from src.amm.router import market_service
from src.governance.service import InMemoryGovernanceService

governance_service = InMemoryGovernanceService(
    market_service=market_service,
    account_service=market_service.account_service,
)
