"""Shared snapshot service instance."""

from src.amm.router import market_service
from src.state.service import StateSnapshotService

snapshot_service = StateSnapshotService(market_service)
