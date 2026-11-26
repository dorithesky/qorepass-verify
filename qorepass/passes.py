"""Passes: the messages issuers and holders sign, and the pass documents.

The contract tells the world exactly what it expects to be signed — every
`*Message` view returns the bytes. This module builds the same bytes locally
(so an issuer can sign offline) and `scripts/verify_encoding.py` proves the
local mirror equals the contract's view on chain.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eth_abi import encode as abi_encode
from eth_abi.packed import encode_packed
from eth_utils import keccak, to_checksum_address

DOMAIN = b"QOREPASS:v1"

A_REGISTER_ISSUER = keccak(text="registerIssuer")
A_ISSUE_PASS = keccak(text="issuePass")
A_CHECK_IN = keccak(text="checkIn")
A_REVOKE_PASS = keccak(text="revokePass")

# ---------------------------------------------------------------------- #
# Selectors
# ---------------------------------------------------------------------- #
SEL_REGISTER_ISSUER = keccak(text="registerIssuer(bytes,bytes,string)")[:4]
SEL_ISSUE_PASS = keccak(text="issuePass(bytes32,address,bytes32,bytes32,bytes32,uint64,bytes)")[:4]
SEL_CHECK_IN = keccak(text="checkIn(bytes32,bytes,bytes)")[:4]
SEL_REVOKE_PASS = keccak(text="revokePass(bytes32,bytes32,bytes)")[:4]
SEL_PASS_INFO = keccak(text="passInfo(bytes32)")[:4]
SEL_PASS_STATE = keccak(text="passState(bytes32)")[:4]
SEL_IS_VALID = keccak(text="isValid(bytes32)")[:4]
SEL_ISSUER_INFO = keccak(text="issuerInfo(address)")[:4]
SEL_ISSUER_NONCE = keccak(text="issuerNonce(address)")[:4]
SEL_TOTAL_ISSUED = keccak(text="totalIssued()")[:4]
SEL_TOTAL_CHECKED_IN = keccak(text="totalCheckedIn()")[:4]
SEL_TOTAL_REVOKED = keccak(text="totalRevoked()")[:4]
SEL_REGISTER_ISSUER_MESSAGE = keccak(text="registerIssuerMessage(address,bytes32)")[:4]
SEL_ISSUE_PASS_MESSAGE = keccak(
    text="issuePassMessage(address,bytes32,address,bytes32,bytes32,bytes32,uint64,uint32)"
)[:4]
SEL_CHECK_IN_MESSAGE = keccak(text="checkInMessage(bytes32,bytes32)")[:4]
SEL_REVOKE_PASS_MESSAGE = keccak(text="revokePassMessage(address,bytes32,bytes32,uint32)")[:4]

STATE_NAMES = {0: "UNKNOWN", 1: "VALID", 2: "CHECKED_IN", 3: "EXPIRED", 4: "REVOKED"}


# ---------------------------------------------------------------------- #
# Messages
# ---------------------------------------------------------------------- #
def register_issuer_message(chain_id: int, registry: str, issuer: str, name_hash: bytes) -> bytes:
    return encode_packed(
        ["bytes", "uint256", "address", "bytes32", "address", "bytes32"],
        [DOMAIN, chain_id, registry, A_REGISTER_ISSUER, issuer, name_hash],
    )


def issue_pass_message(
    chain_id: int,
    registry: str,
    issuer: str,
    pass_id: bytes,
    holder: str,
    event_id: bytes,
    meta_hash: bytes,
    holder_key_hash: bytes,
    valid_until: int,
    approval_nonce: int,
) -> bytes:
    return encode_packed(
        ["bytes", "uint256", "address", "bytes32", "address", "bytes32", "address", "bytes32", "bytes32", "bytes32", "uint64", "uint32"],
        [
            DOMAIN,
            chain_id,
            registry,
            A_ISSUE_PASS,
            issuer,
            pass_id,
            holder,
            event_id,
            meta_hash,
            holder_key_hash,
            valid_until,
            approval_nonce,
        ],
    )


def check_in_message(chain_id: int, registry: str, pass_id: bytes, holder_key_hash: bytes) -> bytes:
    return encode_packed(
        ["bytes", "uint256", "address", "bytes32", "bytes32", "bytes32"],
        [DOMAIN, chain_id, registry, A_CHECK_IN, pass_id, holder_key_hash],
    )


def revoke_pass_message(
    chain_id: int, registry: str, issuer: str, pass_id: bytes, reason_hash: bytes, approval_nonce: int
) -> bytes:
    return encode_packed(
        ["bytes", "uint256", "address", "bytes32", "address", "bytes32", "bytes32", "uint32"],
        [DOMAIN, chain_id, registry, A_REVOKE_PASS, issuer, pass_id, reason_hash, approval_nonce],
    )


# ---------------------------------------------------------------------- #
# Calldata
# ---------------------------------------------------------------------- #
def calldata_register_issuer(pubkey: bytes, signature: bytes, name: str) -> bytes:
    return SEL_REGISTER_ISSUER + abi_encode(["bytes", "bytes", "string"], [pubkey, signature, name])


def calldata_issue_pass(
    pass_id: bytes,
    holder: str,
    event_id: bytes,
    meta_hash: bytes,
    holder_key_hash: bytes,
    valid_until: int,
    signature: bytes,
) -> bytes:
    return SEL_ISSUE_PASS + abi_encode(
        ["bytes32", "address", "bytes32", "bytes32", "bytes32", "uint64", "bytes"],
        [pass_id, holder, event_id, meta_hash, holder_key_hash, valid_until, signature],
    )


def calldata_check_in(pass_id: bytes, holder_pubkey: bytes, holder_signature: bytes) -> bytes:
    return SEL_CHECK_IN + abi_encode(["bytes32", "bytes", "bytes"], [pass_id, holder_pubkey, holder_signature])


def calldata_revoke_pass(pass_id: bytes, reason_hash: bytes, signature: bytes) -> bytes:
    return SEL_REVOKE_PASS + abi_encode(["bytes32", "bytes32", "bytes"], [pass_id, reason_hash, signature])


def calldata_pass_info(pass_id: bytes) -> bytes:
    return SEL_PASS_INFO + abi_encode(["bytes32"], [pass_id])


def calldata_pass_state(pass_id: bytes) -> bytes:
    return SEL_PASS_STATE + abi_encode(["bytes32"], [pass_id])


def calldata_issuer_info(issuer: str) -> bytes:
    return SEL_ISSUER_INFO + abi_encode(["address"], [issuer])


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def new_pass_id() -> bytes:
    return secrets.token_bytes(32)


def event_id_for(name: str) -> bytes:
    return keccak(text=name)


def hash_text(text: str) -> bytes:
    return keccak(text=text)


def hash_metadata(metadata: dict[str, Any]) -> bytes:
    blob = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
    return keccak(blob)


def holder_key_hash(pubkey: bytes) -> bytes:
    return keccak(pubkey)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def from_b64(text: str) -> bytes:
    return base64.b64decode(text)


@dataclass
class PassDocument:
    """The file a holder keeps. Everything in it is public; the secret key is not."""

    pass_id: str
    event_id: str
    event_name: str
    issuer: str
    holder_label: str
    holder_pubkey: str  # base64
    holder_key_hash: str = ""
    holder_address: str = "0x0000000000000000000000000000000000000000"
    meta_hash: str = ""
    valid_until: int = 0
    approval_nonce: int = 0
    issued_at: int = 0
    issuer_pubkey: str = ""  # base64
    issuer_signature: str = ""  # base64
    registry: str = ""
    chain_id: int = 9800
    status: str = "issued"
    tx: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "version": "qorepass/v1",
            "passId": self.pass_id,
            "eventId": self.event_id,
            "eventName": self.event_name,
            "issuer": self.issuer,
            "holder": {
                "label": self.holder_label,
                "address": self.holder_address,
                "pubkey": self.holder_pubkey,
                "keyHash": self.holder_key_hash,
            },
            "metaHash": self.meta_hash,
            "validUntil": self.valid_until,
            "approvalNonce": self.approval_nonce,
            "issuedAt": self.issued_at,
            "issuerPubkey": self.issuer_pubkey,
            "issuerSignature": self.issuer_signature,
            "registry": self.registry,
            "chainId": self.chain_id,
            "status": self.status,
            "tx": self.tx,
            **({"extra": self.extra} if self.extra else {}),
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> "PassDocument":
        raw = json.loads(path.read_text())
        holder = raw.get("holder", {})
        return cls(
            pass_id=raw["passId"],
            event_id=raw.get("eventId", ""),
            event_name=raw.get("eventName", ""),
            issuer=raw.get("issuer", ""),
            holder_label=holder.get("label", ""),
            holder_pubkey=holder.get("pubkey", ""),
            holder_key_hash=holder.get("keyHash", ""),
            holder_address=holder.get("address", "0x0000000000000000000000000000000000000000"),
            meta_hash=raw.get("metaHash", ""),
            valid_until=int(raw.get("validUntil", 0)),
            approval_nonce=int(raw.get("approvalNonce", 0)),
            issued_at=int(raw.get("issuedAt", 0)),
            issuer_pubkey=raw.get("issuerPubkey", ""),
            issuer_signature=raw.get("issuerSignature", ""),
            registry=raw.get("registry", ""),
            chain_id=int(raw.get("chainId", 9800)),
            status=raw.get("status", "issued"),
            tx=raw.get("tx", ""),
            extra=raw.get("extra", {}),
        )

    def issue_message(self) -> bytes:
        """Recompute the exact message the issuer signed for this pass."""
        return issue_pass_message(
            self.chain_id,
            self.registry,
            self.issuer,
            bytes.fromhex(self.pass_id[2:]),
            self.holder_address,
            bytes.fromhex(self.event_id[2:]),
            bytes.fromhex(self.meta_hash[2:]),
            bytes.fromhex(self.holder_key_hash[2:]),
            self.valid_until,
            self.approval_nonce,
        )


def now_ts() -> int:
    return int(time.time())


def checksum(address: str) -> str:
    return to_checksum_address(address)
