#!/usr/bin/env python3
"""Prove the Python mirror of the signed messages equals the contract's view.

Every authorisation in QorePass is a signature over bytes the contract builds in
`*Message` views. The signer builds the same bytes locally so it can work
offline. This script asks the deployed contract for each message and compares it
with the local encoder, byte for byte — the check that keeps the two from
drifting.

    python scripts/verify_encoding.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qorepass import passes as P  # noqa: E402
from qorepass.cli import ZERO, Context  # noqa: E402
from qorepass.config import settings  # noqa: E402

FAILURES: list[str] = []


def check(label: str, local: bytes, onchain: bytes) -> None:
    same = local == onchain
    print(f"{'PASS' if same else 'FAIL'}  {label}  ({len(local)} bytes)")
    if not same:
        print(f"  local   {local.hex()}")
        print(f"  onchain {onchain.hex()}")
        FAILURES.append(label)


def main() -> int:
    ctx = Context(settings())
    registry = ctx.registry
    chain_id = ctx.cfg.evm_chain_id
    issuer = ctx.issuer.evm
    pass_id = bytes(range(32))
    event_id = P.event_id_for("QoreChain Demo Day")
    meta_hash = P.hash_metadata({"tier": "builder"})
    key_hash = bytes(range(32, 64))
    valid_until = 1_800_000_000
    nonce = 7
    name_hash = P.hash_text("QoreChain Demo Day")
    reason = P.hash_text("refunded")

    cases = [
        (
            "registerIssuerMessage",
            P.SEL_REGISTER_ISSUER_MESSAGE,
            abi_encode(["address", "bytes32"], [issuer, name_hash]),
            P.register_issuer_message(chain_id, registry, issuer, name_hash),
        ),
        (
            "issuePassMessage",
            P.SEL_ISSUE_PASS_MESSAGE,
            abi_encode(
                ["address", "bytes32", "address", "bytes32", "bytes32", "bytes32", "uint64", "uint32"],
                [issuer, pass_id, ZERO, event_id, meta_hash, key_hash, valid_until, nonce],
            ),
            P.issue_pass_message(chain_id, registry, issuer, pass_id, ZERO, event_id, meta_hash, key_hash, valid_until, nonce),
        ),
        (
            "checkInMessage",
            P.SEL_CHECK_IN_MESSAGE,
            abi_encode(["bytes32", "bytes32"], [pass_id, key_hash]),
            P.check_in_message(chain_id, registry, pass_id, key_hash),
        ),
        (
            "revokePassMessage",
            P.SEL_REVOKE_PASS_MESSAGE,
            abi_encode(["address", "bytes32", "bytes32", "uint32"], [issuer, pass_id, reason, nonce]),
            P.revoke_pass_message(chain_id, registry, issuer, pass_id, reason, nonce),
        ),
    ]

    for label, selector, args, local in cases:
        raw = ctx.evm.eth_call(registry, selector + args)
        # a `returns (bytes memory)` result is ABI-encoded: offset, length, data, padding
        (onchain,) = abi_decode(["bytes"], bytes.fromhex(raw[2:]))
        check(label, local, onchain)

    if FAILURES:
        print(f"\n{len(FAILURES)} mismatch(es): {FAILURES}")
        return 1
    print("\nlocal encoder matches the contract for all four messages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
