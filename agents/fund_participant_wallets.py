from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from eth_account import Account
from web3 import Web3

from config import load_config
from entromarket_client import ERC20_ABI, EntroMarketClient, VAULT_ABI
from models import AgentWallet


REPORT_PATH = Path(__file__).resolve().parent / "state" / "participant_funding_report.json"


def load_wallets(config, *, start: int, count: int, prefix: str) -> list[AgentWallet]:
    raw = json.loads(Path(config.participant_wallets_file).read_text(encoding="utf-8"))
    selected = raw[max(start - 1, 0) : max(start - 1, 0) + count]
    wallets: list[AgentWallet] = []
    for item in selected:
        wallets.append(
            AgentWallet(
                agent_name=str(item["agent_name"]),
                address=str(item["address"]).lower(),
                private_key=str(item["private_key"]),
                erc8004_agent_id=f"{prefix}/{item['agent_name']}",
            )
        )
    return wallets


def token_units(amount: Decimal) -> int:
    return int(amount * (Decimal(10) ** 18))


def send_eth(web3: Web3, sender: Any, recipient: str, amount_eth: Decimal) -> str:
    tx = {
        "from": sender.address,
        "to": Web3.to_checksum_address(recipient),
        "value": web3.to_wei(amount_eth, "ether"),
    }
    return send_tx(web3, sender, tx, gas_limit=21000)


def send_tx(web3: Web3, sender: Any, tx: dict[str, Any], gas_limit: int = 250000) -> str:
    tx.update(
        {
            "nonce": web3.eth.get_transaction_count(sender.address),
            "chainId": web3.eth.chain_id,
            "gas": gas_limit,
        }
    )
    latest_block = web3.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas")
    if base_fee is None:
        tx["gasPrice"] = web3.eth.gas_price
    else:
        try:
            priority_fee = web3.eth.max_priority_fee
        except Exception:
            priority_fee = web3.to_wei(1, "gwei")
        tx["maxPriorityFeePerGas"] = priority_fee
        tx["maxFeePerGas"] = int(base_fee) * 2 + int(priority_fee)
    signed = web3.eth.account.sign_transaction(tx, sender.key)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180, poll_latency=2)
    if receipt.status != 1:
        raise RuntimeError(f"transaction failed: {Web3.to_hex(tx_hash)}")
    return Web3.to_hex(tx_hash)


def ensure_eth_balance(web3: Web3, sender: Any, wallet: AgentWallet, target_eth: Decimal) -> str | None:
    current = Decimal(web3.from_wei(web3.eth.get_balance(Web3.to_checksum_address(wallet.address)), "ether"))
    if current >= target_eth:
        return None
    return send_eth(web3, sender, wallet.address, target_eth - current)


def ensure_token_balance(web3: Web3, token, sender: Any, wallet: AgentWallet, target_amount: Decimal) -> str | None:
    current = Decimal(token.functions.balanceOf(Web3.to_checksum_address(wallet.address)).call()) / (Decimal(10) ** 18)
    if current >= target_amount:
        return None
    tx = token.functions.transfer(
        Web3.to_checksum_address(wallet.address),
        token_units(target_amount - current),
    ).build_transaction({"from": sender.address})
    return send_tx(web3, sender, tx)


def deposit_and_sync(client: EntroMarketClient, wallet: AgentWallet, asset: str, delta: Decimal) -> dict[str, Any]:
    if delta <= Decimal("0"):
        account = client.get_account(wallet.address) or {"account_id": wallet.address.lower()}
        return {"status": "skipped", "account": account}

    if asset == "usdc":
        tx_hash = client._deposit_stable(wallet.private_key, delta)
    elif asset == "entropy":
        tx_hash = client._deposit_entropy(wallet, delta)
    else:
        raise ValueError(f"unsupported asset: {asset}")

    return client.signed_request(
        "POST",
        "/vault/deposits/sync",
        {
            "account_id": wallet.address.lower(),
            "asset": asset,
            "transaction_hash": tx_hash,
        },
        wallet.private_key,
    )


def ensure_backend_balance(client: EntroMarketClient, wallet: AgentWallet, *, asset: str, target_amount: Decimal) -> dict[str, Any]:
    account = client.get_account(wallet.address) or {}
    balance_key = "usdc_balance" if asset == "usdc" else "entropy_balance"
    current = Decimal(str(account.get(balance_key, "0")))
    if current >= target_amount:
        return {"status": "already_funded", "account": account}
    delta = target_amount - current
    return deposit_and_sync(client, wallet, asset, delta)


def fund_group(
    *,
    web3: Web3,
    client: EntroMarketClient,
    stable,
    entropy,
    sender: Any,
    wallets: list[AgentWallet],
    gas_budget_eth: Decimal,
    onchain_usdnb_target: Decimal,
    backend_usdnb_target: Decimal,
    onchain_entropy_target: Decimal | None = None,
    backend_entropy_target: Decimal | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for wallet in wallets:
        entry: dict[str, Any] = {
            "agent_name": wallet.agent_name,
            "address": wallet.address.lower(),
        }
        entry["usdnb_topup_tx"] = ensure_token_balance(web3, stable, sender, wallet, onchain_usdnb_target)
        entry["eth_for_usdnb_tx"] = ensure_eth_balance(web3, sender, wallet, gas_budget_eth)
        if onchain_entropy_target is not None:
            entry["entropy_topup_tx"] = ensure_token_balance(web3, entropy, sender, wallet, onchain_entropy_target)
        entry["backend_usdnb"] = ensure_backend_balance(client, wallet, asset="usdc", target_amount=backend_usdnb_target)
        if backend_entropy_target is not None:
            entry["eth_for_entropy_tx"] = ensure_eth_balance(web3, sender, wallet, gas_budget_eth)
            entry["backend_entropy"] = ensure_backend_balance(client, wallet, asset="entropy", target_amount=backend_entropy_target)
        results.append(entry)
        print(f"[fund] prepared {wallet.agent_name} ({wallet.address.lower()})", flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Fund proposer/trader participant wallets for the EntroMarket agent swarm.")
    parser.add_argument("--gas-budget-eth", default="0.0018")
    parser.add_argument("--proposer-onchain-usdnb", default="200")
    parser.add_argument("--proposer-backend-usdnb", default="80")
    parser.add_argument("--trader-onchain-usdnb", default="150")
    parser.add_argument("--trader-backend-usdnb", default="100")
    parser.add_argument("--trader-onchain-entropy", default="30")
    parser.add_argument("--trader-backend-entropy", default="20")
    args = parser.parse_args()

    config = load_config()
    client = EntroMarketClient(config)
    web3 = client.web3
    sender_key = os.getenv("FUNDER_PRIVATE_KEY") or os.getenv("PRIVATE_KEY")
    if not sender_key:
        raise RuntimeError("FUNDER_PRIVATE_KEY or PRIVATE_KEY must be configured")
    sender = Account.from_key(sender_key)

    stable = web3.eth.contract(address=Web3.to_checksum_address(config.stable_token_address), abi=ERC20_ABI)
    entropy = web3.eth.contract(address=Web3.to_checksum_address(config.entropy_token_address), abi=ERC20_ABI)
    _vault = web3.eth.contract(address=Web3.to_checksum_address(config.vault_address), abi=VAULT_ABI)

    proposer_wallets = load_wallets(
        config,
        start=config.proposer_wallet_start,
        count=config.proposer_wallet_count,
        prefix=config.proposer_agent_id_prefix,
    )
    trader_wallets = load_wallets(
        config,
        start=config.trader_wallet_start,
        count=config.trader_wallet_count,
        prefix=config.trader_agent_id_prefix,
    )

    gas_budget_eth = Decimal(args.gas_budget_eth)
    proposer_results = fund_group(
        web3=web3,
        client=client,
        stable=stable,
        entropy=entropy,
        sender=sender,
        wallets=proposer_wallets,
        gas_budget_eth=gas_budget_eth,
        onchain_usdnb_target=Decimal(args.proposer_onchain_usdnb),
        backend_usdnb_target=Decimal(args.proposer_backend_usdnb),
    )
    trader_results = fund_group(
        web3=web3,
        client=client,
        stable=stable,
        entropy=entropy,
        sender=sender,
        wallets=trader_wallets,
        gas_budget_eth=gas_budget_eth,
        onchain_usdnb_target=Decimal(args.trader_onchain_usdnb),
        backend_usdnb_target=Decimal(args.trader_backend_usdnb),
        onchain_entropy_target=Decimal(args.trader_onchain_entropy),
        backend_entropy_target=Decimal(args.trader_backend_entropy),
    )

    report = {
        "sender": sender.address,
        "proposers": proposer_results,
        "traders": trader_results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[fund] report written to {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
