"""FastAPI application entrypoint."""

from fastapi import FastAPI

from src.attestation.router import router as attestation_router
from src.auth.router import router as auth_router
from src.amm.router import router as amm_router
from src.governance.router import router as governance_router
from src.state.router import router as state_router
from src.withdrawal.router import router as withdrawal_router
from src.vault.router import router as vault_router

app = FastAPI(
    title="EntroMarket Backend",
    version="0.1.0",
    description="Directional CPMM demo backend for the EntroMarket hackathon prototype.",
)
app.include_router(attestation_router)
app.include_router(auth_router)
app.include_router(amm_router)
app.include_router(governance_router)
app.include_router(state_router)
app.include_router(withdrawal_router)
app.include_router(vault_router)


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    """Return a simple health response."""

    return {"status": "ok"}
