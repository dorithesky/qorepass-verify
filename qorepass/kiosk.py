"""The kiosk key: a linked key that may do exactly one thing.

A venue does not want its door scanner to hold the account's mnemonic. It wants
a key that can check passes in and cannot do anything else — not move a token,
not mint a pass, not change an issuer.

QoreChain's abstract-account lane gives exactly that. The venue links an Ed25519
key to its account with the `evm` permission **and** a spending rule whose
`allowed_evm_calls` names one contract and one selector:

    <registry>/0x<checkIn selector>

so a `MsgExecuteEVM` signed by the kiosk key is executed as the venue account
*only* if it calls `checkIn` on this registry. The kiosk key has no funds: a
relayer pays the fee, and the fee payer cannot change what the kiosk authorised
because the authorisation is bound to the target, the calldata, the value, the
gas limit and the account's per-key auth nonce.

The gate still cannot be bypassed by a stolen kiosk key: `checkIn` itself
requires the holder's ML-DSA-87 signature over `checkInMessage(passId,
holderKeyHash)`. The kiosk can only present a pass; it cannot make one valid.
"""

from __future__ import annotations

import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from qorsdk import derive_unified_account, link_authenticator_msgs, link_proof_ed25519
from qorsdk.authenticator import (
    evm_auth_sign_bytes_v2,
    execute_evm_msg,
    fetch_auth_nonce,
    link_proof_ed25519 as _proof,  # noqa: F401  (re-exported for scripts)
)

from . import passes as P
from .config import ROOT, Settings

KEY_PATH = ROOT / "keys" / "kiosk.key"
PUB_PATH = ROOT / "keys" / "kiosk.pub"
PERMISSIONS = ("evm",)
LABEL = "qorepass-kiosk"


def load_or_create_key() -> Ed25519PrivateKey:
    """The kiosk's Ed25519 key. Throwaway, gitignored, like every other key."""
    if KEY_PATH.exists():
        return Ed25519PrivateKey.from_private_bytes(KEY_PATH.read_bytes())
    key = Ed25519PrivateKey.generate()
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    KEY_PATH.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    KEY_PATH.chmod(0o600)
    PUB_PATH.write_bytes(public_key(key))
    return key


def public_key(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def link_messages(
    *,
    owner: str,
    chain_id: str,
    key: Ed25519PrivateKey,
    registry: str,
    days: int = 30,
    per_tx_limit_uqor: int = 1_000_000,
    daily_limit_uqor: int = 5_000_000,
    now: int | None = None,
) -> list:
    """The two messages the venue signs to link the kiosk key with one call."""
    import time

    pub = public_key(key)
    proof = link_proof_ed25519(
        key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ),
        chain_id=chain_id,
        account_address=owner,
    )
    rule = {
        "id": LABEL,
        "per_tx_limit": per_tx_limit_uqor,
        "daily_limit": daily_limit_uqor,
        "allowed_denoms": ["uqor"],
        # One contract, one selector. A kiosk key that tries to call anything
        # else — a transfer, an issue, another contract — is refused by the
        # chain before the call happens.
        "allowed_evm_calls": [f"{registry}/0x{P.SEL_CHECK_IN.hex()}"],
        "enabled": True,
    }
    return link_authenticator_msgs(
        owner=owner,
        chain_id=chain_id,
        scheme=proof.scheme,
        pubkey=proof.pubkey,
        permissions=list(PERMISSIONS),
        expiry_unix=int(now or time.time()) + days * 86400,
        possession_proof=proof.possession_proof,
        label=LABEL,
        spending_rule=rule,
    )


def window_status(chain, owner: str) -> dict:  # noqa: ANN001 - chain client
    try:
        w = chain.evm_window(owner)
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}
    return {
        "live": w.live,
        "remaining_txs": w.remaining_txs,
        "remaining_blocks": w.remaining_blocks,
        "allowed_targets": list(w.allowed_targets),
    }


def execute_authorised(
    *,
    chain,  # noqa: ANN001
    cfg: Settings,
    key: Ed25519PrivateKey,
    owner_account,  # noqa: ANN001 - unified account of the venue
    relayer,  # noqa: ANN001 - unified account paying the fee
    to: str,
    data: bytes,
    value: str = "0",
    gas_limit: int | None = None,
    memo: str = "qorepass:kiosk",
) -> dict:
    """Run one EVM call as the venue account, authorised by the kiosk key.

    The chain executes it only if the call matches the linked key's spending
    rule (`allowed_evm_calls` = this registry's `checkIn`), so the same function
    doubles as the negative test: point it at another selector and the chain
    refuses before the contract runs.
    """
    gas = gas_limit or cfg.evm_gas_call
    pub = public_key(key)
    nonce = int(fetch_auth_nonce(chain, owner_account.cosmos, pub).nonce)
    digest = evm_auth_sign_bytes_v2(
        cfg.chain_id,
        owner_account.cosmos,
        pub,
        to=to,
        value=value,
        data=data,
        nonce=nonce,
        gas_limit=gas,
    )
    signature = key.sign(digest)
    message = execute_evm_msg(
        relayer=relayer.cosmos,
        account=owner_account.cosmos,
        scheme="ed25519",
        pubkey=pub,
        signature=signature,
        to=to,
        value=value,
        data=data,
        gas_limit=gas,
        nonce=nonce,
    )
    outcome = chain.send_hybrid(relayer, [message], memo=memo)
    executions = chain.execution_results(outcome.tx_hash) if outcome.ok else []
    execution = None
    if executions:
        first = executions[0]
        execution = {
            "success": bool(getattr(first, "success", False)),
            "ret": "0x" + (getattr(first, "ret", b"") or b"").hex(),
            "vm_error": getattr(first, "vm_error", "") or getattr(first, "reason", ""),
        }
    return {
        "tx": outcome.tx_hash,
        "code": outcome.code,
        "raw_log": outcome.raw_log,
        "auth_nonce": nonce,
        "auth_digest": "0x" + digest.hex(),
        "execution": execution,
    }


def check_in_through_kiosk(
    *,
    chain,  # noqa: ANN001
    cfg: Settings,
    key: Ed25519PrivateKey,
    owner_account,  # noqa: ANN001 - unified account of the venue
    relayer,  # noqa: ANN001 - unified account paying the fee
    registry: str,
    pass_id: bytes,
    holder_pubkey: bytes,
    holder_signature: bytes,
    gas_limit: int | None = None,
) -> dict:
    """Check a pass in as the venue, with the kiosk key authorising the call."""
    return execute_authorised(
        chain=chain,
        cfg=cfg,
        key=key,
        owner_account=owner_account,
        relayer=relayer,
        to=registry,
        data=P.calldata_check_in(pass_id, holder_pubkey, holder_signature),
        gas_limit=gas_limit,
        memo=f"qorepass:kiosk-checkin:{pass_id.hex()[:16]}",
    )


def record(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(path.read_text()) if path.exists() else {}
    existing.update(data)
    path.write_text(json.dumps(existing, indent=2) + "\n")
