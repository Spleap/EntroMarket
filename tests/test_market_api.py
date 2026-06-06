"""Integration-style tests for the in-memory market API."""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from eth_account import Account
from eth_account.messages import encode_typed_data
from fastapi.testclient import TestClient

from src.amm.router import market_index_service, market_service
from src.auth.dependencies import request_auth_service
from src.main import app

client = TestClient(app)
_raw_post = client.post
_request_signer = Account.create()


def _build_signed_headers(path: str, body: bytes, method: str = "POST", signer_key=None) -> dict[str, str]:
    signer = _request_signer if signer_key is None else Account.from_key(signer_key)
    payload = request_auth_service.build_request_payload(
        account_id=signer.address.lower(),
        method=method,
        path=path,
        body=body,
        ttl_seconds=300,
    )
    signature = Account.sign_message(
        encode_typed_data(full_message=payload.typed_data),
        signer.key,
    ).signature.to_0x_hex()
    return {
        "content-type": "application/json",
        "x-entro-account": signer.address.lower(),
        "x-entro-nonce": str(payload.nonce),
        "x-entro-expires-at": str(payload.expires_at),
        "x-entro-signature": signature,
    }


def _signed_post(url: str, *args, json: object | None = None, headers: dict[str, str] | None = None, **kwargs):
    if "content" in kwargs:
        body = kwargs["content"]
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
    elif json is None:
        body_bytes = b""
    else:
        body_bytes = json_module.dumps(json, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signed_headers = _build_signed_headers(url, body_bytes)
    merged_headers = {**signed_headers, **(headers or {})}
    return _raw_post(url, *args, content=body_bytes, headers=merged_headers, **kwargs)


json_module = json
client.post = _signed_post


def _signed_get(url: str, *, signer_key=None, headers: dict[str, str] | None = None):
    signed_headers = _build_signed_headers(url, b"", method="GET", signer_key=signer_key)
    merged_headers = {**signed_headers, **(headers or {})}
    return client.get(url, headers=merged_headers)


def _signed_post_as(url: str, signer_key, *, json: object | None = None, headers: dict[str, str] | None = None):
    if json is None:
        body_bytes = b""
    else:
        body_bytes = json_module.dumps(json, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signed_headers = _build_signed_headers(url, body_bytes, signer_key=signer_key)
    merged_headers = {**signed_headers, **(headers or {})}
    return _raw_post(url, content=body_bytes, headers=merged_headers)


def _default_signer_account_id() -> str:
    return _request_signer.address.lower()


def _future_trading_close_at(minutes: int = 10) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _force_market_closed(market_id: str) -> None:
    market = market_service.get_market(market_id)
    market.trading_close_at = datetime.now(timezone.utc) - timedelta(seconds=1)


def _fund_account(account_id: str, amount: str) -> None:
    response = client.post(f"/amm/accounts/{account_id}/deposit-usdc", json={"amount": amount})
    assert response.status_code == 200


def _create_market_for_default_signer(
    title: str,
    *,
    seed_amount: str = "100",
    description: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
):
    creator_account_id = _default_signer_account_id()
    _fund_account(creator_account_id, str(Decimal(seed_amount) * 2))
    response = client.post(
        "/amm/markets",
        json={
            "title": title,
            "description": description,
            "creator_account_id": creator_account_id,
            "category": category,
            "tags": tags or [],
            "trading_close_at": _future_trading_close_at(),
            "yes_liquidity": seed_amount,
            "no_liquidity": seed_amount,
        },
    )
    assert response.status_code == 200
    return response


def test_create_market_and_fetch_it() -> None:
    creator_account_id = _default_signer_account_id()
    response = _create_market_for_default_signer(
        "ETH above 5000 by year end",
        seed_amount="100",
        description="Demo market",
        category="crypto",
        tags=["ethereum", "layer1"],
    )
    payload = response.json()
    assert payload["title"] == "ETH above 5000 by year end"
    assert payload["state"]["probability_yes"] == "0.5"

    detail = client.get(f"/amm/markets/{payload['market_id']}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["market_id"] == payload["market_id"]
    assert detail_payload["creator_account_id"] == creator_account_id
    assert detail_payload["category"] == "crypto"
    assert detail_payload["tags"] == ["ethereum", "layer1"]
    assert detail_payload["trading_close_at"]
    assert "state" not in detail_payload

    search = client.get("/amm/markets", params={"q": "5000"})
    assert search.status_code == 200
    search_payload = search.json()
    assert any(item["market_id"] == payload["market_id"] for item in search_payload)
    assert all("state" not in item for item in search_payload)

    tag_search = client.get("/amm/markets/search", params={"tag": "ethereum"})
    assert tag_search.status_code == 200
    assert any(item["market_id"] == payload["market_id"] for item in tag_search.json())

    creator_search = client.get("/amm/markets/search", params={"creator_account_id": creator_account_id})
    assert creator_search.status_code == 200
    assert any(item["market_id"] == payload["market_id"] for item in creator_search.json())

    category_search = client.get("/amm/markets/search", params={"category": "crypto"})
    assert category_search.status_code == 200
    assert any(item["market_id"] == payload["market_id"] for item in category_search.json())


def test_trade_updates_persisted_market_state() -> None:
    create_response = _create_market_for_default_signer("BTC above 150k")
    market = create_response.json()
    market_id = market["market_id"]

    buy_response = client.post(
        f"/amm/markets/{market_id}/buy-yes",
        json={"share_amount": "10"},
    )
    assert buy_response.status_code == 200
    trade_payload = buy_response.json()
    assert Decimal(trade_payload["trade"]["probability_yes_after"]) > Decimal(
        trade_payload["trade"]["probability_yes_before"]
    )

    detail = client.get(f"/amm/markets/{market_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["market_id"] == market_id
    assert detail_payload["status"] == "open"
    assert "state" not in detail_payload

    search = client.get("/amm/markets", params={"q": "150k"})
    assert search.status_code == 200
    assert any(item["market_id"] == market_id for item in search.json())


def test_public_market_endpoints_hide_unresolved_orphan_index_rows() -> None:
    orphan_market_id = "orphan-open-market"
    now = datetime.now(timezone.utc)
    market_index_service.upsert_market(
        market_id=orphan_market_id,
        title="Orphan open market",
        description="Should not stay visible without runtime backing",
        creator_account_id="orphan-creator",
        category="debug",
        tags=["orphan"],
        created_at=now,
        trading_close_at=now + timedelta(minutes=30),
        updated_at=now,
        status="open",
        resolved_outcome=None,
        resolved_at=None,
    )

    list_response = client.get("/amm/markets", params={"q": "Orphan open market"})
    assert list_response.status_code == 200
    assert all(item["market_id"] != orphan_market_id for item in list_response.json())

    detail_response = client.get(f"/amm/markets/{orphan_market_id}")
    assert detail_response.status_code == 404

    with_index_response = client.get("/amm/markets", params={"q": "Orphan open market"})
    assert with_index_response.status_code == 200
    assert all(item["market_id"] != orphan_market_id for item in with_index_response.json())


def test_probability_query_charges_entropy_balance() -> None:
    account_id = "query-user"
    deposit_response = client.post(
        f"/amm/accounts/{account_id}/deposit-entropy",
        json={"amount": "5"},
    )
    assert deposit_response.status_code == 200

    create_response = _create_market_for_default_signer("SOL above 500")
    market_id = create_response.json()["market_id"]

    query_response = client.post(
        f"/amm/markets/{market_id}/query-probability",
        json={
            "account_id": account_id,
            "entropy_fee": "0.75",
        },
    )
    assert query_response.status_code == 200
    payload = query_response.json()
    assert payload["entropy_fee_charged"] == "0.75"
    assert payload["account"]["entropy_balance"] == "4.25"
    assert payload["account"]["total_entropy_spent"] == "0.75"
    assert payload["market"]["state"]["collected_information_tax"] == "0.75"


def test_account_trade_updates_usdc_and_position() -> None:
    account_id = "trader-1"
    deposit_response = client.post(
        f"/amm/accounts/{account_id}/deposit-usdc",
        json={"amount": "30"},
    )
    assert deposit_response.status_code == 200

    create_response = _create_market_for_default_signer("ARB above 5")
    market_id = create_response.json()["market_id"]

    buy_response = client.post(
        f"/amm/markets/{market_id}/accounts/{account_id}/buy-yes",
        json={"share_amount": "5"},
    )
    assert buy_response.status_code == 200
    buy_payload = buy_response.json()
    assert Decimal(buy_payload["account"]["usdc_balance"]) < Decimal("30")
    assert buy_payload["position"]["yes_shares"] == "5"

    sell_response = client.post(
        f"/amm/markets/{market_id}/accounts/{account_id}/sell-yes",
        json={"share_amount": "2"},
    )
    assert sell_response.status_code == 200
    sell_payload = sell_response.json()
    assert sell_payload["position"]["yes_shares"] == "3"

    position_response = client.get(f"/amm/accounts/{account_id}/markets/{market_id}/position")
    assert position_response.status_code == 200
    assert position_response.json()["yes_shares"] == "3"


def test_resolve_and_settle_market_account() -> None:
    account_id = "settle-user"
    deposit_response = client.post(
        f"/amm/accounts/{account_id}/deposit-usdc",
        json={"amount": "20"},
    )
    assert deposit_response.status_code == 200

    create_response = _create_market_for_default_signer("OP above 10")
    market_id = create_response.json()["market_id"]

    buy_response = client.post(
        f"/amm/markets/{market_id}/accounts/{account_id}/buy-yes",
        json={"share_amount": "4"},
    )
    assert buy_response.status_code == 200
    balance_after_buy = Decimal(buy_response.json()["account"]["usdc_balance"])

    _force_market_closed(market_id)
    resolve_response = client.post(
        f"/amm/markets/{market_id}/resolve",
        json={"outcome": "yes"},
    )
    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "resolved"

    settle_response = client.post(f"/amm/markets/{market_id}/accounts/{account_id}/settle")
    assert settle_response.status_code == 200
    settlement_payload = settle_response.json()
    assert settlement_payload["payout"] == "4"
    assert Decimal(settlement_payload["account"]["usdc_balance"]) == balance_after_buy + Decimal("4")
    assert settlement_payload["position"]["yes_shares"] == "0"


def test_account_can_use_existing_balance_to_become_directional_lp() -> None:
    lp_signer = Account.create()
    lp_account_id = lp_signer.address.lower()
    fee_account_id = "probability-buyer"

    deposit_response = client.post(
        f"/amm/accounts/{lp_account_id}/deposit-usdc",
        json={"amount": "20"},
    )
    assert deposit_response.status_code == 200
    client.post(f"/amm/accounts/{fee_account_id}/deposit-entropy", json={"amount": "5"})

    create_response = _create_market_for_default_signer("SEI above 2")
    market_id = create_response.json()["market_id"]

    trade_response = client.post(
        f"/amm/markets/{market_id}/buy-yes",
        json={"share_amount": "8"},
    )
    assert trade_response.status_code == 200

    lp_response = _signed_post_as(
        f"/amm/markets/{market_id}/accounts/{lp_account_id}/add-liquidity",
        lp_signer.key,
        json={
            "side": "yes",
            "amount": "6",
        },
    )
    assert lp_response.status_code == 200
    lp_payload = lp_response.json()
    assert lp_payload["account"]["usdc_balance"] == "14"
    assert lp_payload["lp_position"]["provider_id"] == lp_account_id
    assert lp_payload["lp_position"]["side"] == "yes"
    assert lp_payload["lp_position"]["amount"] == "6"

    query_response = client.post(
        f"/amm/markets/{market_id}/query-probability",
        json={
            "account_id": fee_account_id,
            "entropy_fee": "1.2",
        },
    )
    assert query_response.status_code == 200

    _force_market_closed(market_id)
    resolve_response = client.post(
        f"/amm/markets/{market_id}/resolve",
        json={"outcome": "yes"},
    )
    assert resolve_response.status_code == 200
    resolve_payload = resolve_response.json()
    assert resolve_payload["market_id"] == market_id

    account_response = client.get(f"/amm/accounts/{lp_account_id}")
    assert account_response.status_code == 200
    account_payload = account_response.json()
    assert account_payload["usdc_balance"] == "20"
    assert Decimal(account_payload["entropy_balance"]) > Decimal("0")


def test_market_must_be_closed_before_resolution() -> None:
    agent_accounts = [f"timed-agent-{index}" for index in range(5)]
    agent_ids = [f"agent://timed/{index}" for index in range(5)]
    client.post("/amm/accounts/timed-market-author/deposit-usdc", json={"amount": "200"})
    for index, agent_account in enumerate(agent_accounts):
        client.post(f"/amm/accounts/{agent_account}/deposit-entropy", json={"amount": "100000"})
        stake_response = client.post(
            "/governance/agents/stake",
            json={
                "account_id": agent_account,
                "amount": "100000",
                "erc8004_agent_id": agent_ids[index],
            },
        )
        assert stake_response.status_code == 200

    proposal_response = client.post(
        "/governance/market-proposals",
        json={
            "proposer_account_id": "timed-market-author",
            "title": "Time-gated resolution",
            "description": "Resolution should only start after close",
            "trading_close_at": _future_trading_close_at(),
            "yes_liquidity": "100",
            "no_liquidity": "100",
        },
    )
    assert proposal_response.status_code == 200
    proposal_id = proposal_response.json()["proposal_id"]

    for agent_id in agent_ids:
        vote_response = client.post(
            f"/governance/market-proposals/{proposal_id}/votes",
            json={"erc8004_agent_id": agent_id, "vote": "approve"},
        )
        assert vote_response.status_code == 200

    market_id = client.post(f"/governance/market-proposals/{proposal_id}/finalize").json()["created_market"]["market_id"]
    resolution_response = client.post(
        "/governance/resolution-proposals",
        json={
            "proposer_account_id": "timed-resolver",
            "market_id": market_id,
            "proposed_outcome": "yes",
        },
    )
    assert resolution_response.status_code == 400
    assert "trading_close_at" in resolution_response.json()["detail"]


def test_session_buy_and_query_probability() -> None:
    signer = Account.create()
    account_id = signer.address.lower()

    client.post(f"/amm/accounts/{account_id}/deposit-usdc", json={"amount": "25"})
    client.post(f"/amm/accounts/{account_id}/deposit-entropy", json={"amount": "5"})

    _fund_account(account_id, "200")
    market_response = _signed_post_as(
        "/amm/markets",
        signer.key,
        json={
            "title": "TIA above 25",
            "creator_account_id": account_id,
            "trading_close_at": _future_trading_close_at(),
            "yes_liquidity": "100",
            "no_liquidity": "100",
        },
    )
    market_id = market_response.json()["market_id"]

    payload_response = client.post(
        "/auth/session-payload",
        json={
            "account_id": account_id,
            "delegate_id": "frontend-session",
            "allowed_actions": ["buy_yes", "query_probability"],
            "max_usdc": "15",
            "max_entropy": "2",
            "ttl_seconds": 600,
        },
    )
    assert payload_response.status_code == 200
    payload = payload_response.json()

    signed = Account.sign_message(
        encode_typed_data(full_message=payload["typed_data"]),
        signer.key,
    )
    session_response = client.post(
        "/auth/sessions",
        json={
            "account_id": account_id,
            "delegate_id": "frontend-session",
            "allowed_actions": ["buy_yes", "query_probability"],
            "max_usdc": "15",
            "max_entropy": "2",
            "nonce": payload["nonce"],
            "expires_at": payload["expires_at"],
            "signature": signed.signature.to_0x_hex(),
        },
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    buy_response = client.post(
        f"/amm/markets/{market_id}/session/buy-yes",
        json={
            "session_id": session_id,
            "share_amount": "4",
        },
    )
    assert buy_response.status_code == 200
    buy_payload = buy_response.json()
    assert buy_payload["position"]["yes_shares"] == "4"

    query_response = client.post(
        f"/amm/markets/{market_id}/session/query-probability",
        json={
            "session_id": session_id,
            "entropy_fee": "0.5",
        },
    )
    assert query_response.status_code == 200
    query_payload = query_response.json()
    assert query_payload["entropy_fee_charged"] == "0.5"
    assert query_payload["account"]["entropy_balance"] == "4.5"

    session_detail = client.get(f"/auth/sessions/{session_id}")
    assert session_detail.status_code == 200
    session_payload = session_detail.json()
    assert Decimal(session_payload["remaining_usdc"]) < Decimal("15")
    assert session_payload["remaining_entropy"] == "1.5"


def test_state_snapshot_and_account_proof_api() -> None:
    account_id = "proof-user"
    client.post(f"/amm/accounts/{account_id}/deposit-usdc", json={"amount": "20"})
    client.post(f"/amm/accounts/{account_id}/deposit-entropy", json={"amount": "2"})

    market_response = _create_market_for_default_signer("SUI above 3")
    market_id = market_response.json()["market_id"]
    client.post(
        f"/amm/markets/{market_id}/accounts/{account_id}/buy-yes",
        json={"share_amount": "3"},
    )

    snapshot_response = client.post("/state/snapshot")
    assert snapshot_response.status_code == 200
    snapshot_payload = snapshot_response.json()
    assert snapshot_payload["leaf_count"] >= 1
    assert snapshot_payload["merkle_root"]

    proof_response = client.get(f"/state/proof/{account_id}")
    assert proof_response.status_code == 200
    proof_payload = proof_response.json()
    assert proof_payload["account_id"] == account_id
    assert proof_payload["merkle_root"] == snapshot_payload["merkle_root"]
    assert proof_payload["proof_valid"] is True


def test_account_proof_bundle_api() -> None:
    signer = Account.create()
    account_id = signer.address.lower()
    client.post(f"/amm/accounts/{account_id}/deposit-usdc", json={"amount": "7"})
    client.post(f"/amm/accounts/{account_id}/deposit-entropy", json={"amount": "1.25"})

    proof_bundle_response = _signed_get(
        f"/state/proof-bundles/{account_id}",
        signer_key=signer.key,
    )
    assert proof_bundle_response.status_code == 200
    payload = proof_bundle_response.json()
    assert payload["snapshot"]["snapshot_id"] == payload["proof"]["snapshot_id"]
    assert payload["snapshot"]["merkle_root"] == payload["proof"]["merkle_root"]
    assert payload["proof"]["account_id"] == account_id
    assert payload["proof"]["proof_valid"] is True
    assert payload["state_root_signature"]["snapshot_id"] == payload["snapshot"]["snapshot_id"]
    assert payload["state_root_signature"]["merkle_root"] == payload["snapshot"]["merkle_root"]
    assert payload["state_root_signature"]["signature_valid"] is True


def test_attestation_and_state_root_signature_api() -> None:
    snapshot_response = client.post("/state/snapshot")
    assert snapshot_response.status_code == 200
    snapshot_payload = snapshot_response.json()

    attestation_response = client.get("/attestation")
    assert attestation_response.status_code == 200
    attestation_payload = attestation_response.json()
    assert attestation_payload["signature_valid"] is True
    assert attestation_payload["merkle_root"] == snapshot_payload["merkle_root"]
    assert attestation_payload["operator_address"].startswith("0x")

    state_root_response = client.get("/attestation/state-root-signature")
    assert state_root_response.status_code == 200
    state_root_payload = state_root_response.json()
    assert state_root_payload["signature_valid"] is True
    assert state_root_payload["merkle_root"] == snapshot_payload["merkle_root"]
    assert state_root_payload["operator_address"] == attestation_payload["operator_address"]
    assert state_root_payload["payload"]["signature_kind"] == "evm_state_root"
    assert state_root_payload["payload"]["vault"] == state_root_payload["vault_address"]
    assert state_root_payload["payload"]["chain_id"] == state_root_payload["chain_id"]


def test_create_withdrawal_intent_api() -> None:
    account_id = "withdraw-user"
    deposit_response = client.post(
        f"/amm/accounts/{account_id}/deposit-usdc",
        json={"amount": "12"},
    )
    assert deposit_response.status_code == 200

    withdraw_response = client.post(
        "/withdrawals",
        json={
            "account_id": account_id,
            "destination_address": "0x2222222222222222222222222222222222222222",
            "asset": "usdc",
            "amount": "3.5",
        },
    )
    assert withdraw_response.status_code == 200
    payload = withdraw_response.json()
    assert payload["account"]["usdc_balance"] == "8.5"
    assert payload["withdrawal"]["amount"] == "3.5"
    assert payload["withdrawal"]["amount_units"] == 3500000000000000000
    assert payload["withdrawal"]["signature_valid"] is True
    assert payload["withdrawal"]["payload"]["signature_kind"] == "evm_withdrawal"
    assert payload["withdrawal"]["payload"]["vault"] == payload["withdrawal"]["vault_address"]

    detail_response = client.get(f"/withdrawals/{payload['withdrawal']['withdrawal_id']}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["signature_valid"] is True
    assert detail_payload["destination_address"] == "0x2222222222222222222222222222222222222222"


def test_governance_market_review_and_resolution_flow() -> None:
    agent_accounts = [f"gov-agent-{index}" for index in range(5)]
    agent_ids = [f"agent://gov/{index}" for index in range(5)]
    client.post("/amm/accounts/market-author/deposit-usdc", json={"amount": "200"})
    for index, agent_account in enumerate(agent_accounts):
        deposit_response = client.post(
            f"/amm/accounts/{agent_account}/deposit-entropy",
            json={"amount": "100000"},
        )
        assert deposit_response.status_code == 200
        stake_response = client.post(
            "/governance/agents/stake",
            json={
                "account_id": agent_account,
                "amount": "100000",
                "erc8004_agent_id": agent_ids[index],
            },
        )
        assert stake_response.status_code == 200
        assert stake_response.json()["is_eligible"] is True
        assert stake_response.json()["account"]["staked_entropy"] == "100000"

    proposal_response = client.post(
        "/governance/market-proposals",
        json={
            "proposer_account_id": "market-author",
            "title": "DOGE above 1",
            "description": "AI Agent DAO reviewed market",
            "category": "memecoin",
            "tags": ["doge", "ai-review"],
            "trading_close_at": _future_trading_close_at(),
            "yes_liquidity": "100",
            "no_liquidity": "100",
        },
    )
    assert proposal_response.status_code == 200
    proposal_id = proposal_response.json()["proposal_id"]

    for agent_id in agent_ids:
        vote_response = client.post(
            f"/governance/market-proposals/{proposal_id}/votes",
            json={
                "erc8004_agent_id": agent_id,
                "vote": "approve",
            },
        )
        assert vote_response.status_code == 200

    finalize_response = client.post(f"/governance/market-proposals/{proposal_id}/finalize")
    assert finalize_response.status_code == 200
    finalize_payload = finalize_response.json()
    assert finalize_payload["proposal"]["status"] == "approved"
    assert finalize_payload["proposal"]["category"] == "memecoin"
    assert finalize_payload["proposal"]["tags"] == ["doge", "ai-review"]
    market_id = finalize_payload["created_market"]["market_id"]
    assert finalize_payload["created_market"]["creator_account_id"] == "market-author"
    assert finalize_payload["created_market"]["category"] == "memecoin"
    assert finalize_payload["created_market"]["tags"] == ["doge", "ai-review"]
    _force_market_closed(market_id)

    resolution_response = client.post(
        "/governance/resolution-proposals",
        json={
            "proposer_account_id": "resolver-1",
            "market_id": market_id,
            "proposed_outcome": "yes",
        },
    )
    assert resolution_response.status_code == 200
    resolution_proposal_id = resolution_response.json()["proposal_id"]

    for agent_id in agent_ids:
        vote_response = client.post(
            f"/governance/resolution-proposals/{resolution_proposal_id}/votes",
            json={
                "erc8004_agent_id": agent_id,
                "vote": "no_veto",
            },
        )
        assert vote_response.status_code == 200

    finalize_resolution_response = client.post(
        f"/governance/resolution-proposals/{resolution_proposal_id}/finalize"
    )
    assert finalize_resolution_response.status_code == 200
    finalize_resolution_payload = finalize_resolution_response.json()
    assert finalize_resolution_payload["proposal"]["status"] == "executed"
    assert finalize_resolution_payload["market"]["status"] == "resolved"

    public_market_response = client.get(f"/amm/markets/{market_id}")
    assert public_market_response.status_code == 200
    public_market_payload = public_market_response.json()
    assert public_market_payload["status"] == "resolved"
    assert public_market_payload["resolved_outcome"] == "yes"
    assert "state" not in public_market_payload


def test_governance_resolution_fallback_slashes_and_rewards_agents() -> None:
    agent_accounts = [f"fallback-agent-{index}" for index in range(5)]
    agent_ids = [f"agent://fallback/{index}" for index in range(5)]
    client.post("/amm/accounts/market-author-2/deposit-usdc", json={"amount": "200"})
    for index, agent_account in enumerate(agent_accounts):
        client.post(f"/amm/accounts/{agent_account}/deposit-entropy", json={"amount": "100000"})
        stake_response = client.post(
            "/governance/agents/stake",
            json={
                "account_id": agent_account,
                "amount": "100000",
                "erc8004_agent_id": agent_ids[index],
            },
        )
        assert stake_response.status_code == 200

    proposal_response = client.post(
        "/governance/market-proposals",
        json={
            "proposer_account_id": "market-author-2",
            "title": "PEPE above 1",
            "description": "Fallback flow",
            "trading_close_at": _future_trading_close_at(),
            "yes_liquidity": "100",
            "no_liquidity": "100",
        },
    )
    proposal_id = proposal_response.json()["proposal_id"]
    for agent_id in agent_ids:
        client.post(
            f"/governance/market-proposals/{proposal_id}/votes",
            json={"erc8004_agent_id": agent_id, "vote": "approve"},
        )
    market_id = client.post(f"/governance/market-proposals/{proposal_id}/finalize").json()["created_market"]["market_id"]
    _force_market_closed(market_id)

    resolution_response = client.post(
        "/governance/resolution-proposals",
        json={
            "proposer_account_id": "resolver-2",
            "market_id": market_id,
            "proposed_outcome": "yes",
        },
    )
    resolution_proposal_id = resolution_response.json()["proposal_id"]

    for agent_id in agent_ids[:3]:
        vote_response = client.post(
            f"/governance/resolution-proposals/{resolution_proposal_id}/votes",
            json={"erc8004_agent_id": agent_id, "vote": "veto"},
        )
        assert vote_response.status_code == 200
    for agent_id in agent_ids[3:]:
        vote_response = client.post(
            f"/governance/resolution-proposals/{resolution_proposal_id}/votes",
            json={"erc8004_agent_id": agent_id, "vote": "no_veto"},
        )
        assert vote_response.status_code == 200

    finalize_resolution_response = client.post(
        f"/governance/resolution-proposals/{resolution_proposal_id}/finalize"
    )
    assert finalize_resolution_response.status_code == 200
    assert finalize_resolution_response.json()["proposal"]["status"] == "vetoed"
    assert finalize_resolution_response.json()["market"] is None

    fallback_response = client.post(
        f"/governance/resolution-proposals/{resolution_proposal_id}/fallback",
        json={
            "final_outcome": "no",
            "reason": "Fallback oracle confirms NO",
        },
    )
    assert fallback_response.status_code == 200
    fallback_payload = fallback_response.json()
    assert fallback_payload["proposal"]["status"] == "fallback_executed"
    assert fallback_payload["market"]["status"] == "resolved"
    assert fallback_payload["proposal"]["fallback_outcome"] == "no"
    assert fallback_payload["slashed_total"] == "1000.000"
    assert len(fallback_payload["rewarded_agents"]) == 3
    assert len(fallback_payload["slashed_agents"]) == 2

    slashed_agent = client.get(f"/governance/agents/{urllib.parse.quote(agent_ids[3], safe='')}")
    rewarded_agent = client.get(f"/governance/agents/{urllib.parse.quote(agent_ids[0], safe='')}")
    assert slashed_agent.status_code == 200
    assert rewarded_agent.status_code == 200
    assert slashed_agent.json()["account"]["staked_entropy"] == "99500.000"
    assert rewarded_agent.json()["account"]["entropy_balance"].startswith("333.333333333333333333333333")
