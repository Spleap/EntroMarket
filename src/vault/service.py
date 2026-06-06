"""Minimal on-chain vault adapter for real deposits and withdrawals."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from threading import Lock

from eth_account import Account
from web3 import Web3

from src.amm.account_service import Account as LedgerAccount
from src.amm.account_service import InMemoryAccountService
from src.attestation.service import AttestationService, ZERO_ADDRESS
from src.withdrawal.service import WithdrawalAsset, WithdrawalIntent, WithdrawalService

VAULT_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "user", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "asset", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "Deposited",
        "type": "event",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "name": "executedWithdrawals",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "withdrawalId", "type": "bytes32"},
            {"internalType": "address", "name": "recipient", "type": "address"},
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "uint256", "name": "expiry", "type": "uint256"},
            {"internalType": "bytes", "name": "signature", "type": "bytes"},
        ],
        "name": "executeWithdrawal",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "snapshotId", "type": "bytes32"},
            {"internalType": "bytes32", "name": "merkleRoot", "type": "bytes32"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "bytes", "name": "signature", "type": "bytes"},
        ],
        "name": "submitStateRoot",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


@dataclass(slots=True)
class DepositSyncResult:
    """One on-chain deposit synced into the internal ledger."""

    account: LedgerAccount
    account_id: str
    depositor_address: str
    asset: WithdrawalAsset
    amount: Decimal
    amount_units: int
    transaction_hash: str
    block_number: int
    synced_at: datetime


@dataclass(slots=True)
class WithdrawalExecutionResult:
    """One operator-signed withdrawal executed on-chain."""

    withdrawal: WithdrawalIntent
    transaction_hash: str
    block_number: int
    executed_at: datetime


@dataclass(slots=True)
class StateRootSubmissionResult:
    """One freshly signed state root submitted on-chain."""

    snapshot_id: str
    merkle_root: str
    timestamp: datetime
    operator_address: str
    vault_address: str
    chain_id: int
    signature: str
    payload: dict
    transaction_hash: str
    block_number: int
    submitted_at: datetime


class VaultService:
    """Verify real deposits and relay signed withdrawals to the vault contract."""

    def __init__(
        self,
        account_service: InMemoryAccountService,
        withdrawal_service: WithdrawalService,
        attestation_service: AttestationService,
    ) -> None:
        self.account_service = account_service
        self.withdrawal_service = withdrawal_service
        self.attestation_service = attestation_service
        self.rpc_url = os.getenv("ENTRO_RPC_URL", "http://127.0.0.1:8545")
        self.chain_id = int(os.getenv("ENTRO_CHAIN_ID", "31337"))
        self.vault_address = self._normalize_address(os.getenv("ENTRO_VAULT_ADDRESS", ZERO_ADDRESS))
        self.stable_token_address = self._normalize_address(
            os.getenv("USDNB_TOKEN_ADDRESS")
            or os.getenv("STABLE_TOKEN_ADDRESS")
            or ZERO_ADDRESS
        )
        self.entropy_token_address = self._normalize_address(os.getenv("ENTROPY_TOKEN_ADDRESS", ZERO_ADDRESS))
        private_key = os.getenv("PRIVATE_KEY", "")
        if private_key and not private_key.startswith("0x"):
            private_key = f"0x{private_key}"
        self.relayer_private_key = private_key or None
        self._processed_deposit_hashes: set[str] = set()
        self._lock = Lock()

    def sync_deposit(self, *, account_id: str, asset: WithdrawalAsset, transaction_hash: str) -> DepositSyncResult:
        """Read one vault deposit tx from chain and credit the internal ledger."""

        self._require_configured_chain()
        normalized_account = account_id.lower()
        normalized_hash = Web3.to_hex(Web3.to_bytes(hexstr=transaction_hash))
        with self._lock:
            if normalized_hash in self._processed_deposit_hashes:
                raise ValueError("deposit transaction already synced")

        web3 = self._web3()
        vault = web3.eth.contract(address=Web3.to_checksum_address(self.vault_address), abi=VAULT_ABI)
        receipt = web3.eth.get_transaction_receipt(normalized_hash)
        if receipt.status != 1:
            raise ValueError("deposit transaction failed on-chain")
        transaction = web3.eth.get_transaction(normalized_hash)
        if not transaction["to"] or self._normalize_address(transaction["to"]) != self.vault_address:
            raise ValueError("transaction was not sent to the configured vault")

        deposit_events = vault.events.Deposited().process_receipt(receipt)
        if not deposit_events:
            raise ValueError("no vault deposit event found in transaction receipt")
        matching_asset = self._resolve_asset_address(asset)
        matching_event = None
        for event in deposit_events:
            if self._normalize_address(event["args"]["asset"]) == matching_asset:
                matching_event = event
                break
        if matching_event is None:
            raise ValueError("deposit receipt does not contain the expected asset")

        depositor_address = self._normalize_address(matching_event["args"]["user"])
        if depositor_address != normalized_account:
            raise ValueError("on-chain depositor does not match account_id")
        amount_units = int(matching_event["args"]["amount"])
        amount = self._from_token_units(amount_units)
        if asset == WithdrawalAsset.USDC:
            account = self.account_service.deposit_usdc(normalized_account, amount)
        else:
            account = self.account_service.deposit_entropy(normalized_account, amount)

        with self._lock:
            self._processed_deposit_hashes.add(normalized_hash)

        return DepositSyncResult(
            account=account,
            account_id=normalized_account,
            depositor_address=depositor_address,
            asset=asset,
            amount=amount,
            amount_units=amount_units,
            transaction_hash=normalized_hash,
            block_number=int(receipt.blockNumber),
            synced_at=datetime.now(timezone.utc),
        )

    def execute_withdrawal(self, withdrawal_id: str) -> WithdrawalExecutionResult:
        """Broadcast one stored withdrawal intent to the configured vault."""

        self._require_configured_chain(require_private_key=True)
        intent = self.withdrawal_service.get_withdrawal(withdrawal_id)
        web3 = self._web3()
        vault = web3.eth.contract(address=Web3.to_checksum_address(self.vault_address), abi=VAULT_ABI)
        withdrawal_key = Web3.to_bytes(hexstr=f"0x{intent.withdrawal_id}")
        if vault.functions.executedWithdrawals(withdrawal_key).call():
            raise ValueError("withdrawal already executed on-chain")

        relayer = Account.from_key(self.relayer_private_key)
        tx = vault.functions.executeWithdrawal(
            withdrawal_key,
            Web3.to_checksum_address(intent.destination_address),
            Web3.to_checksum_address(intent.asset_address),
            int(intent.amount_units),
            int(intent.expiry),
            Web3.to_bytes(hexstr=intent.signature),
        ).build_transaction(
            self._build_fee_aware_transaction(web3, sender=relayer.address, gas=350000)
        )
        signed = web3.eth.account.sign_transaction(tx, self.relayer_private_key)
        tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise ValueError("withdrawal execution transaction failed")
        updated_intent = self.withdrawal_service.mark_executed(intent.withdrawal_id, Web3.to_hex(tx_hash))
        return WithdrawalExecutionResult(
            withdrawal=updated_intent,
            transaction_hash=Web3.to_hex(tx_hash),
            block_number=int(receipt.blockNumber),
            executed_at=updated_intent.executed_at or datetime.now(timezone.utc),
        )

    def submit_latest_state_root(self) -> StateRootSubmissionResult:
        """Build a fresh snapshot, sign its root, and anchor it on-chain."""

        self._require_configured_chain(require_private_key=True)
        snapshot = self.attestation_service.snapshot_service.build_snapshot()
        signed_root = self.attestation_service.sign_latest_state_root()
        if signed_root.snapshot_id != snapshot.snapshot_id or signed_root.merkle_root != snapshot.merkle_root:
            raise ValueError("signed state root does not match latest snapshot")

        web3 = self._web3()
        vault = web3.eth.contract(address=Web3.to_checksum_address(self.vault_address), abi=VAULT_ABI)
        relayer = Account.from_key(self.relayer_private_key)
        tx = vault.functions.submitStateRoot(
            Web3.to_bytes(hexstr=signed_root.payload["snapshot_id"]),
            Web3.to_bytes(hexstr=signed_root.payload["merkle_root"]),
            int(signed_root.payload["timestamp"]),
            Web3.to_bytes(hexstr=signed_root.signature),
        ).build_transaction(
            self._build_fee_aware_transaction(web3, sender=relayer.address, gas=300000)
        )
        signed_tx = web3.eth.account.sign_transaction(tx, self.relayer_private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise ValueError("state root submission transaction failed")
        submitted_at = datetime.now(timezone.utc)
        return StateRootSubmissionResult(
            snapshot_id=signed_root.snapshot_id,
            merkle_root=signed_root.merkle_root,
            timestamp=signed_root.timestamp,
            operator_address=signed_root.operator_address,
            vault_address=signed_root.vault_address,
            chain_id=signed_root.chain_id,
            signature=signed_root.signature,
            payload=signed_root.payload,
            transaction_hash=Web3.to_hex(tx_hash),
            block_number=int(receipt.blockNumber),
            submitted_at=submitted_at,
        )

    def _web3(self) -> Web3:
        web3 = Web3(Web3.HTTPProvider(self.rpc_url))
        if not web3.is_connected():
            raise ValueError("failed to connect to configured EVM RPC")
        return web3

    def _build_fee_aware_transaction(self, web3: Web3, *, sender: str, gas: int) -> dict:
        latest_block = web3.eth.get_block("latest")
        tx = {
            "from": sender,
            "nonce": web3.eth.get_transaction_count(sender),
            "chainId": self.chain_id,
            "gas": gas,
        }
        base_fee = latest_block.get("baseFeePerGas")
        if base_fee is None:
            tx["gasPrice"] = web3.eth.gas_price
            return tx

        try:
            priority_fee = web3.eth.max_priority_fee
        except Exception:
            priority_fee = web3.to_wei(1, "gwei")
        tx["maxPriorityFeePerGas"] = priority_fee
        tx["maxFeePerGas"] = int(base_fee) * 2 + int(priority_fee)
        return tx

    def get_relayer_address(self) -> str | None:
        if not self.relayer_private_key:
            return None
        return Account.from_key(self.relayer_private_key).address.lower()

    def _require_configured_chain(self, *, require_private_key: bool = False) -> None:
        if self.vault_address == ZERO_ADDRESS:
            raise ValueError("ENTRO_VAULT_ADDRESS is not configured")
        if self.stable_token_address == ZERO_ADDRESS:
            raise ValueError("USDNB_TOKEN_ADDRESS is not configured")
        if self.entropy_token_address == ZERO_ADDRESS:
            raise ValueError("ENTROPY_TOKEN_ADDRESS is not configured")
        if require_private_key and not self.relayer_private_key:
            raise ValueError("PRIVATE_KEY is not configured for withdrawal execution")

    def _resolve_asset_address(self, asset: WithdrawalAsset) -> str:
        if asset == WithdrawalAsset.USDC:
            return self.stable_token_address
        return self.entropy_token_address

    def _from_token_units(self, amount_units: int, decimals: int = 18) -> Decimal:
        return Decimal(amount_units) / (Decimal(10) ** decimals)

    def _normalize_address(self, address: str) -> str:
        return Web3.to_checksum_address(address).lower()
