"""Software attestation and operator signatures for the mock TEE."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak, to_checksum_address

from src.auth.service import InMemorySessionAuthService
from src.state.service import StateSnapshotService

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
WITHDRAWAL_TYPEHASH = keccak(
    text="Withdrawal(bytes32 withdrawalId,address recipient,address asset,uint256 amount,uint256 expiry,address vault,uint256 chainId)"
)
STATE_ROOT_TYPEHASH = keccak(
    text="StateRoot(bytes32 snapshotId,bytes32 merkleRoot,uint256 timestamp,address vault,uint256 chainId)"
)


@dataclass(slots=True)
class StateRootSignature:
    """Signed latest state root payload."""

    snapshot_id: str
    merkle_root: str
    timestamp: datetime
    operator_address: str
    vault_address: str
    chain_id: int
    signature: str
    payload: dict


@dataclass(slots=True)
class AttestationDocument:
    """Signed software attestation payload."""

    operator_address: str
    operator_public_key: str
    boot_time: datetime
    code_hash: str
    config_hash: str
    snapshot_id: str
    merkle_root: str
    signature: str
    payload: dict


class AttestationService:
    """Produce signed software attestation documents."""

    def __init__(self, snapshot_service: StateSnapshotService, project_root: Path) -> None:
        self.snapshot_service = snapshot_service
        self.project_root = project_root
        operator_private_key = os.getenv("OPERATOR_PRIVATE_KEY", "").strip()
        if operator_private_key:
            if not operator_private_key.startswith("0x"):
                operator_private_key = f"0x{operator_private_key}"
            self.operator_account = Account.from_key(operator_private_key)
        else:
            self.operator_account = Account.create()
        self.boot_time = datetime.now(timezone.utc)
        self.chain_id = int(os.getenv("ENTRO_CHAIN_ID", "11155111"))
        self.vault_address = self._normalize_address(os.getenv("ENTRO_VAULT_ADDRESS", ZERO_ADDRESS))

    def get_attestation(self) -> AttestationDocument:
        """Return the current attestation document."""

        snapshot = self.snapshot_service.get_latest_snapshot()
        payload = {
            "operator_address": self.operator_account.address.lower(),
            "operator_public_key": self.operator_account._key_obj.public_key.to_hex(),
            "boot_time": self.boot_time.isoformat(),
            "code_hash": self._compute_code_hash(),
            "config_hash": self._compute_config_hash(),
            "snapshot_id": snapshot.snapshot_id,
            "merkle_root": snapshot.merkle_root,
        }
        signature = self._sign_payload(payload)
        return AttestationDocument(
            operator_address=payload["operator_address"],
            operator_public_key=payload["operator_public_key"],
            boot_time=self.boot_time,
            code_hash=payload["code_hash"],
            config_hash=payload["config_hash"],
            snapshot_id=payload["snapshot_id"],
            merkle_root=payload["merkle_root"],
            signature=signature,
            payload=payload,
        )

    def sign_latest_state_root(self) -> StateRootSignature:
        """Return a signed latest state root payload."""

        snapshot = self.snapshot_service.get_latest_snapshot()
        timestamp = datetime.now(timezone.utc)
        payload, signature = self._build_state_root_signature(
            snapshot_id=snapshot.snapshot_id,
            merkle_root=snapshot.merkle_root,
            timestamp=int(timestamp.timestamp()),
        )
        return StateRootSignature(
            snapshot_id=snapshot.snapshot_id,
            merkle_root=snapshot.merkle_root,
            timestamp=timestamp,
            operator_address=self.operator_account.address.lower(),
            vault_address=self.vault_address,
            chain_id=self.chain_id,
            signature=signature,
            payload=payload,
        )

    def verify_signature(self, payload: dict, signature: str) -> bool:
        """Recover the signer and verify it matches the operator."""

        kind = payload.get("signature_kind")
        if kind == "evm_withdrawal":
            recovered = Account.recover_message(
                encode_defunct(primitive=self._hash_withdrawal_payload(payload)),
                signature=signature,
            )
        elif kind == "evm_state_root":
            recovered = Account.recover_message(
                encode_defunct(primitive=self._hash_state_root_payload(payload)),
                signature=signature,
            )
        else:
            recovered = Account.recover_message(
                encode_defunct(text=self._serialize_payload(payload)),
                signature=signature,
            )
        return recovered.lower() == self.operator_account.address.lower()

    def sign_payload(self, payload: dict) -> str:
        """Sign an arbitrary canonical JSON payload with the operator key."""

        return self._sign_payload(payload)

    def sign_withdrawal_payload(
        self,
        *,
        withdrawal_id: str,
        recipient: str,
        asset: str,
        amount: int,
        expiry: int,
        account_id: str | None = None,
        nonce: int | None = None,
        created_at: str | None = None,
    ) -> tuple[dict, str]:
        """Sign a withdrawal payload that matches the Solidity vault hash."""

        payload = {
            "signature_kind": "evm_withdrawal",
            "withdrawal_id": self._format_bytes32(withdrawal_id),
            "recipient": self._normalize_address(recipient),
            "asset": self._normalize_address(asset),
            "amount": str(amount),
            "expiry": int(expiry),
            "vault": self.vault_address,
            "chain_id": self.chain_id,
            "operator_address": self.operator_account.address.lower(),
        }
        if account_id is not None:
            payload["account_id"] = account_id.lower()
        if nonce is not None:
            payload["nonce"] = nonce
        if created_at is not None:
            payload["created_at"] = created_at
        message_hash = self._hash_withdrawal_payload(payload)
        payload["message_hash"] = f"0x{message_hash.hex()}"
        return payload, self._sign_evm_hash(message_hash)

    def get_operator_address(self) -> str:
        """Return the operator address."""

        return self.operator_account.address.lower()

    def _compute_code_hash(self) -> str:
        hasher = sha256()
        file_paths = sorted(self.project_root.glob("src/**/*.py"))
        requirements_file = self.project_root / "requirements.txt"
        if requirements_file.exists():
            file_paths.append(requirements_file)
        for file_path in file_paths:
            relative_path = file_path.relative_to(self.project_root).as_posix()
            hasher.update(relative_path.encode("utf-8"))
            hasher.update(file_path.read_bytes())
        return hasher.hexdigest()

    def _compute_config_hash(self) -> str:
        payload = {
            "attestation_chain_id": self.chain_id,
            "attestation_vault_address": self.vault_address,
            "session_domain_name": InMemorySessionAuthService.DOMAIN_NAME,
            "session_domain_version": InMemorySessionAuthService.DOMAIN_VERSION,
            "session_chain_id": InMemorySessionAuthService.CHAIN_ID,
            "session_verifying_contract": InMemorySessionAuthService.VERIFYING_CONTRACT,
        }
        return sha256(self._serialize_payload(payload).encode("utf-8")).hexdigest()

    def _build_state_root_signature(
        self,
        *,
        snapshot_id: str,
        merkle_root: str,
        timestamp: int,
    ) -> tuple[dict, str]:
        payload = {
            "signature_kind": "evm_state_root",
            "snapshot_id": self._format_bytes32(snapshot_id),
            "merkle_root": self._format_bytes32(merkle_root),
            "timestamp": int(timestamp),
            "vault": self.vault_address,
            "chain_id": self.chain_id,
            "operator_address": self.operator_account.address.lower(),
        }
        message_hash = self._hash_state_root_payload(payload)
        payload["message_hash"] = f"0x{message_hash.hex()}"
        return payload, self._sign_evm_hash(message_hash)

    def _sign_payload(self, payload: dict) -> str:
        signed = Account.sign_message(
            encode_defunct(text=self._serialize_payload(payload)),
            self.operator_account.key,
        )
        return signed.signature.to_0x_hex()

    def _sign_evm_hash(self, message_hash: bytes) -> str:
        signed = Account.sign_message(
            encode_defunct(primitive=message_hash),
            self.operator_account.key,
        )
        return signed.signature.to_0x_hex()

    def _hash_withdrawal_payload(self, payload: dict) -> bytes:
        encoded = encode(
            [
                "bytes32",
                "bytes32",
                "address",
                "address",
                "uint256",
                "uint256",
                "address",
                "uint256",
            ],
            [
                WITHDRAWAL_TYPEHASH,
                self._coerce_bytes32(payload["withdrawal_id"]),
                self._normalize_address(payload["recipient"]),
                self._normalize_address(payload["asset"]),
                int(payload["amount"]),
                int(payload["expiry"]),
                self._normalize_address(payload["vault"]),
                int(payload["chain_id"]),
            ],
        )
        return keccak(encoded)

    def _hash_state_root_payload(self, payload: dict) -> bytes:
        encoded = encode(
            [
                "bytes32",
                "bytes32",
                "bytes32",
                "uint256",
                "address",
                "uint256",
            ],
            [
                STATE_ROOT_TYPEHASH,
                self._coerce_bytes32(payload["snapshot_id"]),
                self._coerce_bytes32(payload["merkle_root"]),
                int(payload["timestamp"]),
                self._normalize_address(payload["vault"]),
                int(payload["chain_id"]),
            ],
        )
        return keccak(encoded)

    def _coerce_bytes32(self, value: str) -> bytes:
        normalized = value[2:] if value.startswith("0x") else value
        if len(normalized) != 64:
            raise ValueError("expected 32-byte hex value")
        return bytes.fromhex(normalized)

    def _format_bytes32(self, value: str) -> str:
        normalized = value[2:] if value.startswith("0x") else value
        if len(normalized) != 64:
            raise ValueError("expected 32-byte hex value")
        return f"0x{normalized.lower()}"

    def _normalize_address(self, address: str) -> str:
        return to_checksum_address(address).lower()

    def _serialize_payload(self, payload: dict) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
