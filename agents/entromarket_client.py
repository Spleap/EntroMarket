from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from threading import Lock
from typing import Any

import requests
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

from config import AgentRuntimeConfig, ReviewerConfig
from models import AgentWallet, ReviewerWallet

ERC20_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

VAULT_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "amount", "type": "uint256"}],
        "name": "depositStable",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "amount", "type": "uint256"}],
        "name": "depositEntropy",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


class EntroMarketClient:
    # Allow enough ETH for approve + deposit under fluctuating Sepolia gas prices.
    MIN_WALLET_GAS_ETH = Decimal("0.006")

    def __init__(self, config: AgentRuntimeConfig | ReviewerConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.web3 = Web3(Web3.HTTPProvider(config.sepolia_rpc_url))
        self._nonce_locks: dict[str, Lock] = defaultdict(Lock)
        self._next_nonce_by_account: dict[str, int] = {}
        self.entropy = self.web3.eth.contract(
            address=Web3.to_checksum_address(config.entropy_token_address),
            abi=ERC20_ABI,
        )
        self.stable = self.web3.eth.contract(
            address=Web3.to_checksum_address(config.stable_token_address),
            abi=ERC20_ABI,
        )
        self.vault = self.web3.eth.contract(
            address=Web3.to_checksum_address(config.vault_address),
            abi=VAULT_ABI,
        )

    def list_market_review_proposals(self) -> list[dict[str, Any]]:
        response = self.session.get(f"{self.config.backend_base_url}/governance/market-proposals", timeout=20)
        response.raise_for_status()
        return response.json()

    def list_markets(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        response = self.session.get(f"{self.config.backend_base_url}/amm/markets", params=params, timeout=20)
        response.raise_for_status()
        return response.json()

    def search_markets(
        self,
        *,
        query: str | None = None,
        status: str | None = None,
        category: str | None = None,
        tag: str | None = None,
        creator_account_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["q"] = query
        if status:
            params["status"] = status
        if category:
            params["category"] = category
        if tag:
            params["tag"] = tag
        if creator_account_id:
            params["creator_account_id"] = creator_account_id
        response = self.session.get(f"{self.config.backend_base_url}/amm/markets/search", params=params, timeout=20)
        response.raise_for_status()
        return response.json()

    def get_market(self, market_id: str) -> dict[str, Any]:
        response = self.session.get(f"{self.config.backend_base_url}/amm/markets/{market_id}", timeout=20)
        response.raise_for_status()
        return response.json()

    def list_agents(self) -> list[dict[str, Any]]:
        response = self.session.get(f"{self.config.backend_base_url}/governance/agents", timeout=20)
        response.raise_for_status()
        return response.json()

    def list_resolution_proposals(self) -> list[dict[str, Any]]:
        response = self.session.get(f"{self.config.backend_base_url}/governance/resolution-proposals", timeout=20)
        response.raise_for_status()
        return response.json()

    def get_market_review_proposal(self, proposal_id: str) -> dict[str, Any]:
        response = self.session.get(
            f"{self.config.backend_base_url}/governance/market-proposals/{proposal_id}",
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def get_resolution_proposal(self, proposal_id: str) -> dict[str, Any]:
        response = self.session.get(
            f"{self.config.backend_base_url}/governance/resolution-proposals/{proposal_id}",
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def get_agent(self, reference: str) -> dict[str, Any] | None:
        response = self.session.get(
            f"{self.config.backend_base_url}/governance/agents/{requests.utils.quote(reference, safe='')}",
            timeout=20,
        )
        if response.status_code in {404, 500}:
            return None
        response.raise_for_status()
        return response.json()

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        response = self.session.get(
            f"{self.config.backend_base_url}/amm/accounts/{account_id.lower()}",
            timeout=20,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def get_position(self, account_id: str, market_id: str) -> dict[str, Any] | None:
        response = self.session.get(
            f"{self.config.backend_base_url}/amm/accounts/{account_id.lower()}/markets/{market_id}/position",
            timeout=20,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def vote_market_review(self, proposal_id: str, wallet: AgentWallet | ReviewerWallet, vote: str) -> dict[str, Any]:
        return self.signed_request(
            "POST",
            f"/governance/market-proposals/{proposal_id}/votes",
            {
                "erc8004_agent_id": wallet.erc8004_agent_id,
                "vote": vote,
            },
            wallet.private_key,
        )

    def finalize_market_review(self, proposal_id: str, wallet: AgentWallet | ReviewerWallet) -> dict[str, Any]:
        return self.signed_request(
            "POST",
            f"/governance/market-proposals/{proposal_id}/finalize",
            None,
            wallet.private_key,
        )

    def create_market_review_proposal(
        self,
        private_key: str,
        *,
        title: str,
        description: str,
        category: str,
        tags: list[str],
        trading_close_at: str,
        yes_liquidity: str,
        no_liquidity: str,
    ) -> dict[str, Any]:
        account = Account.from_key(private_key)
        return self.signed_request(
            "POST",
            "/governance/market-proposals",
            {
                "proposer_account_id": account.address.lower(),
                "title": title,
                "description": description,
                "category": category,
                "tags": tags,
                "trading_close_at": trading_close_at,
                "yes_liquidity": yes_liquidity,
                "no_liquidity": no_liquidity,
            },
            private_key,
        )

    def create_resolution_proposal(
        self,
        wallet: AgentWallet | ReviewerWallet,
        market_id: str,
        proposed_outcome: str,
    ) -> dict[str, Any]:
        return self.signed_request(
            "POST",
            "/governance/resolution-proposals",
            {
                "proposer_account_id": wallet.address.lower(),
                "market_id": market_id,
                "proposed_outcome": proposed_outcome,
            },
            wallet.private_key,
        )

    def vote_resolution_proposal(self, proposal_id: str, wallet: AgentWallet | ReviewerWallet, vote: str) -> dict[str, Any]:
        return self.signed_request(
            "POST",
            f"/governance/resolution-proposals/{proposal_id}/votes",
            {
                "erc8004_agent_id": wallet.erc8004_agent_id,
                "vote": vote,
            },
            wallet.private_key,
        )

    def finalize_resolution_proposal(self, proposal_id: str, wallet: AgentWallet | ReviewerWallet) -> dict[str, Any]:
        return self.signed_request(
            "POST",
            f"/governance/resolution-proposals/{proposal_id}/finalize",
            None,
            wallet.private_key,
        )

    def bootstrap_reviewer(self, wallet: AgentWallet | ReviewerWallet) -> dict[str, Any]:
        return self.bootstrap_governance_agent(wallet)

    def bootstrap_governance_agent(self, wallet: AgentWallet | ReviewerWallet, target_amount: Decimal = Decimal("100000")) -> dict[str, Any]:
        existing = None
        for agent in self.list_agents():
            if agent["account_id"] == wallet.address.lower():
                existing = agent
                break
        if existing is None:
            existing = self.get_agent(wallet.erc8004_agent_id)
        if existing is not None and existing["controller_address"] == wallet.address.lower():
            wallet.erc8004_agent_id = existing["erc8004_agent_id"]
        if existing is not None and existing["is_eligible"]:
            return existing

        account = self.get_account(wallet.address) or {}
        current_entropy = Decimal(str(account.get("entropy_balance", "0")))
        if current_entropy < target_amount:
            delta = target_amount - current_entropy
            self._ensure_wallet_entropy(wallet, delta)
            tx_hash = self._deposit_entropy(wallet, delta)
            self.signed_request(
                "POST",
                "/vault/deposits/sync",
                {
                    "account_id": wallet.address.lower(),
                    "asset": "entropy",
                    "transaction_hash": tx_hash,
                },
                wallet.private_key,
            )

        return self.signed_request(
            "POST",
            "/governance/agents/stake",
            {
                "account_id": wallet.address.lower(),
                "amount": str(target_amount),
                "erc8004_agent_id": wallet.erc8004_agent_id,
            },
            wallet.private_key,
        )

    def signed_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | list[Any] | None,
        private_key: str,
    ) -> dict[str, Any]:
        account = Account.from_key(private_key)
        payload = self.session.post(
            f"{self.config.backend_base_url}/auth/request-payload",
            json={
                "account_id": account.address.lower(),
                "method": method.upper(),
                "path": path,
                "body": body,
                "ttl_seconds": 300,
            },
            timeout=20,
        )
        payload.raise_for_status()
        typed_payload = payload.json()
        signature = Account.sign_message(
            encode_typed_data(full_message=typed_payload["typed_data"]),
            private_key,
        ).signature.to_0x_hex()
        headers = {
            "x-entro-account": account.address.lower(),
            "x-entro-nonce": str(typed_payload["nonce"]),
            "x-entro-expires-at": str(typed_payload["expires_at"]),
            "x-entro-signature": signature,
        }
        data = self._canonical_body(body)
        if method.upper() != "GET":
            headers["Content-Type"] = "application/json"
        response = self.session.request(
            method.upper(),
            f"{self.config.backend_base_url}{path}",
            data=data if method.upper() != "GET" else None,
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        return response.json() if response.content else {}

    def buy_yes(self, private_key: str, market_id: str, share_amount: str) -> dict[str, Any]:
        account = Account.from_key(private_key)
        return self.signed_request(
            "POST",
            f"/amm/markets/{market_id}/accounts/{account.address.lower()}/buy-yes",
            {"share_amount": share_amount},
            private_key,
        )

    def buy_no(self, private_key: str, market_id: str, share_amount: str) -> dict[str, Any]:
        account = Account.from_key(private_key)
        return self.signed_request(
            "POST",
            f"/amm/markets/{market_id}/accounts/{account.address.lower()}/buy-no",
            {"share_amount": share_amount},
            private_key,
        )

    def sell_yes(self, private_key: str, market_id: str, share_amount: str) -> dict[str, Any]:
        account = Account.from_key(private_key)
        return self.signed_request(
            "POST",
            f"/amm/markets/{market_id}/accounts/{account.address.lower()}/sell-yes",
            {"share_amount": share_amount},
            private_key,
        )

    def sell_no(self, private_key: str, market_id: str, share_amount: str) -> dict[str, Any]:
        account = Account.from_key(private_key)
        return self.signed_request(
            "POST",
            f"/amm/markets/{market_id}/accounts/{account.address.lower()}/sell-no",
            {"share_amount": share_amount},
            private_key,
        )

    def add_liquidity(self, private_key: str, market_id: str, side: str, amount: str) -> dict[str, Any]:
        account = Account.from_key(private_key)
        return self.signed_request(
            "POST",
            f"/amm/markets/{market_id}/accounts/{account.address.lower()}/add-liquidity",
            {"side": side, "amount": amount},
            private_key,
        )

    def query_probability(self, private_key: str, market_id: str, entropy_fee: str) -> dict[str, Any]:
        account = Account.from_key(private_key)
        return self.signed_request(
            "POST",
            f"/amm/markets/{market_id}/query-probability",
            {"account_id": account.address.lower(), "entropy_fee": entropy_fee},
            private_key,
        )

    def settle_account(self, private_key: str, market_id: str) -> dict[str, Any]:
        account = Account.from_key(private_key)
        return self.signed_request(
            "POST",
            f"/amm/markets/{market_id}/accounts/{account.address.lower()}/settle",
            None,
            private_key,
        )

    def _deposit_entropy(self, wallet: AgentWallet | ReviewerWallet, amount: Decimal) -> str:
        account = Account.from_key(wallet.private_key)
        amount_units = self._token_units_up(amount)

        approve_tx = self.entropy.functions.approve(
            Web3.to_checksum_address(self.config.vault_address),
            amount_units,
        ).build_transaction({"from": account.address})
        self._send_transaction(account, approve_tx)

        self._ensure_wallet_eth(wallet, self.MIN_WALLET_GAS_ETH)
        deposit_tx = self.vault.functions.depositEntropy(amount_units).build_transaction({"from": account.address})
        return self._send_transaction(account, deposit_tx)

    def ensure_usdnb_ledger_balance(self, private_key: str, required_amount: Decimal) -> dict[str, Any]:
        account = Account.from_key(private_key)
        current = self.get_account(account.address) or {}
        current_balance = Decimal(str(current.get("usdc_balance", "0")))
        if current_balance >= required_amount:
            return current

        deficit = required_amount - current_balance
        wallet = AgentWallet(
            agent_name=account.address.lower(),
            address=account.address.lower(),
            private_key=private_key,
            erc8004_agent_id=f"participant://auto-funding/{account.address.lower()}",
        )
        self._ensure_wallet_eth(wallet, self.MIN_WALLET_GAS_ETH)
        self._ensure_wallet_stable(wallet, deficit)
        tx_hash = self._deposit_stable(private_key, deficit)
        return self.signed_request(
            "POST",
            "/vault/deposits/sync",
            {
                "account_id": account.address.lower(),
                "asset": "usdc",
                "transaction_hash": tx_hash,
            },
            private_key,
        )

    def ensure_entropy_ledger_balance(self, private_key: str, required_amount: Decimal) -> dict[str, Any]:
        account = Account.from_key(private_key)
        current = self.get_account(account.address) or {}
        current_balance = Decimal(str(current.get("entropy_balance", "0")))
        if current_balance >= required_amount:
            return current

        deficit = required_amount - current_balance
        wallet = AgentWallet(
            agent_name=account.address.lower(),
            address=account.address.lower(),
            private_key=private_key,
            erc8004_agent_id=f"participant://auto-funding/{account.address.lower()}",
        )
        self._ensure_wallet_eth(wallet, self.MIN_WALLET_GAS_ETH)
        self._ensure_wallet_entropy(wallet, deficit)
        tx_hash = self._deposit_entropy(wallet, deficit)
        return self.signed_request(
            "POST",
            "/vault/deposits/sync",
            {
                "account_id": account.address.lower(),
                "asset": "entropy",
                "transaction_hash": tx_hash,
            },
            private_key,
        )

    def _deposit_stable(self, private_key: str, amount: Decimal) -> str:
        account = Account.from_key(private_key)
        amount_units = self._token_units_up(amount)
        wallet = AgentWallet(
            agent_name=account.address.lower(),
            address=account.address.lower(),
            private_key=private_key,
            erc8004_agent_id=f"participant://auto-funding/{account.address.lower()}",
        )

        approve_tx = self.stable.functions.approve(
            Web3.to_checksum_address(self.config.vault_address),
            amount_units,
        ).build_transaction({"from": account.address})
        self._send_transaction(account, approve_tx)

        self._ensure_wallet_eth(wallet, self.MIN_WALLET_GAS_ETH)
        deposit_tx = self.vault.functions.depositStable(amount_units).build_transaction({"from": account.address})
        return self._send_transaction(account, deposit_tx)

    def _ensure_wallet_stable(self, wallet: AgentWallet | ReviewerWallet, amount_needed: Decimal) -> None:
        wallet_checksum = Web3.to_checksum_address(wallet.address)
        current_onchain = Decimal(self.web3.from_wei(self.stable.functions.balanceOf(wallet_checksum).call(), "ether"))
        if current_onchain >= amount_needed:
            return
        shortfall = amount_needed - current_onchain
        if not self.config.funder_private_key:
            raise RuntimeError(f"wallet {wallet.address} needs {shortfall} USDNB top-up but no funder key is configured")

        funder = Account.from_key(self.config.funder_private_key)
        transfer_tx = self.stable.functions.transfer(
            Web3.to_checksum_address(wallet.address),
            self._token_units_up(shortfall),
        ).build_transaction({"from": funder.address})
        self._send_transaction(funder, transfer_tx)

    def _ensure_wallet_eth(self, wallet: AgentWallet | ReviewerWallet, target_eth: Decimal) -> None:
        wallet_checksum = Web3.to_checksum_address(wallet.address)
        current_balance = Decimal(self.web3.from_wei(self.web3.eth.get_balance(wallet_checksum), "ether"))
        if current_balance >= target_eth:
            return
        shortfall = target_eth - current_balance
        if not self.config.funder_private_key:
            raise RuntimeError(f"wallet {wallet.address} needs {shortfall} ETH top-up but no funder key is configured")

        funder = Account.from_key(self.config.funder_private_key)
        transfer_tx = {
            "to": wallet_checksum,
            "value": self.web3.to_wei(shortfall, "ether"),
            "gas": 21000,
        }
        self._send_transaction(funder, transfer_tx)

    def _ensure_wallet_entropy(self, wallet: AgentWallet | ReviewerWallet, amount_needed: Decimal) -> None:
        wallet_checksum = Web3.to_checksum_address(wallet.address)
        current_onchain = Decimal(self.web3.from_wei(self.entropy.functions.balanceOf(wallet_checksum).call(), "ether"))
        if current_onchain >= amount_needed:
            return
        shortfall = amount_needed - current_onchain
        if not self.config.funder_private_key:
            raise RuntimeError(f"wallet {wallet.address} needs {shortfall} ENTROPY top-up but no funder key is configured")

        funder = Account.from_key(self.config.funder_private_key)
        transfer_tx = self.entropy.functions.transfer(
            Web3.to_checksum_address(wallet.address),
            self._token_units_up(shortfall),
        ).build_transaction({"from": funder.address})
        self._send_transaction(funder, transfer_tx)

    def _send_transaction(self, account: Any, tx: dict[str, Any]) -> str:
        account_key = str(account.address).lower()
        with self._nonce_locks[account_key]:
            for attempt in range(3):
                built_tx = dict(tx)
                built_tx.update(
                    {
                        "from": account.address,
                        "nonce": self._reserve_nonce(account.address),
                        "chainId": self.web3.eth.chain_id,
                    }
                )
                latest_block = self.web3.eth.get_block("latest")
                base_fee = latest_block.get("baseFeePerGas")
                if base_fee is None:
                    built_tx["gasPrice"] = self.web3.eth.gas_price
                else:
                    try:
                        priority_fee = self.web3.eth.max_priority_fee
                    except Exception:
                        priority_fee = self.web3.to_wei(1, "gwei")
                    built_tx["maxPriorityFeePerGas"] = priority_fee
                    built_tx["maxFeePerGas"] = int(base_fee) * 2 + int(priority_fee)
                built_tx.setdefault("gas", 250000)

                signed = self.web3.eth.account.sign_transaction(built_tx, account.key)
                try:
                    tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
                    receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180, poll_latency=2)
                    if receipt.status != 1:
                        raise RuntimeError(f"on-chain transaction failed: {Web3.to_hex(tx_hash)}")
                    return Web3.to_hex(tx_hash)
                except Exception as exc:
                    message = str(exc).lower()
                    if "replacement transaction underpriced" not in message and "nonce too low" not in message:
                        raise
                    self._next_nonce_by_account[account_key] = self.web3.eth.get_transaction_count(account.address, "pending")
                    if attempt == 2:
                        raise
            raise RuntimeError(f"failed to send transaction for {account.address}")

    def _reserve_nonce(self, address: str) -> int:
        account_key = str(address).lower()
        network_nonce = self.web3.eth.get_transaction_count(address, "pending")
        cached_nonce = self._next_nonce_by_account.get(account_key)
        if cached_nonce is None or cached_nonce < network_nonce:
            nonce = network_nonce
        else:
            nonce = cached_nonce
        self._next_nonce_by_account[account_key] = nonce + 1
        return nonce

    @staticmethod
    def proposal_close_at(proposal: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(str(proposal["trading_close_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)

    @staticmethod
    def _token_units(amount: Decimal) -> int:
        return int(amount * (Decimal(10) ** 18))

    @staticmethod
    def _token_units_up(amount: Decimal) -> int:
        if amount <= Decimal("0"):
            return 0
        scaled = amount * (Decimal(10) ** 18)
        units = int(scaled.to_integral_value(rounding=ROUND_CEILING))
        return max(units, 1)

    @staticmethod
    def _canonical_body(body: dict[str, Any] | list[Any] | None) -> bytes:
        if body is None:
            return b""
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
