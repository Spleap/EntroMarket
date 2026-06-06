# EntroMarket

EntroMarket is a prediction market backend designed for hackathon-grade demos and AI-native trading flows.

It uses a mock-TEE architecture:

- off-chain internal ledger for fast matching and balance updates
- signed API requests for authenticated market actions
- minimal on-chain trust boundary for vault custody and state commitment
- free market discovery, but paid real-time probability queries

## What Is Included

- FastAPI backend under `src/`
- AMM market services and governance flows
- request-signing and authentication modules
- state snapshot and attestation endpoints
- Hardhat contracts under `evm/`
- Python and JavaScript tests

## What Is Not Included

This public repository excludes live deployment secrets and runtime artifacts:

- real private keys
- live VPS deployment credentials
- local databases and runtime state
- live Sepolia operation scripts that depend on private secrets

## Local Development

1. Create an environment file from `.env.backend.example`
2. Install Python dependencies
3. Start the API server

```bash
pip install -r requirements.txt
cp .env.backend.example .env.backend
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

## Smart Contracts

Contracts and local EVM tests live in `evm/`.

```bash
cd evm
npm install
npx hardhat test
```

## Testing

```bash
pytest
```

## Architecture

EntroMarket is built around a simple split:

- on-chain: vault custody, token interactions, minimal trust anchor
- off-chain: order flow, market state, governance review, query charging, internal balances

This keeps the demo fast while preserving a verifiable boundary that can later be upgraded to a real TEE-backed operator.

## License

MIT
