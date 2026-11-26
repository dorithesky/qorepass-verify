"""Decode a contract revert into the contract's own words.

The registry reverts with custom errors (`HolderKeyMismatch()`,
`AlreadyCheckedIn(bytes32,uint64)`, …). A failed EVM transaction stores no
reason, so the reason is recovered by replaying the same calldata one block
earlier with `eth_call` and decoding what comes back.
"""

from __future__ import annotations

import json
from pathlib import Path

from eth_abi import decode as abi_decode
from eth_utils import keccak

ARTIFACT = Path(__file__).resolve().parents[1] / "contracts" / "out" / "QorePassRegistry.sol" / "QorePassRegistry.json"


def _errors() -> dict[str, tuple[str, list[str]]]:
    if not ARTIFACT.exists():
        return {}
    abi = json.loads(ARTIFACT.read_text())["abi"]
    table: dict[str, tuple[str, list[str]]] = {}
    for item in abi:
        if item.get("type") != "error":
            continue
        signature = f"{item['name']}({','.join(i['type'] for i in item.get('inputs', []))})"
        table[keccak(text=signature)[:4].hex()] = (
            item["name"],
            [i["type"] for i in item.get("inputs", [])],
        )
    return table


ERRORS = _errors()


def decode_revert_data(data: str) -> str:
    body = (data or "").removeprefix("0x")
    if len(body) < 8:
        return "reverted (no data)"
    selector, rest = body[:8], body[8:]
    entry = ERRORS.get(selector)
    if not entry:
        return f"reverted (unknown error 0x{selector})"
    name, types = entry
    if not types:
        return f"{name}()"
    try:
        values = abi_decode(types, bytes.fromhex(rest))
    except Exception:
        return f"{name}(…)"
    return f"{name}({', '.join(_show(v) for v in values)})"


def _show(value: object) -> str:
    if isinstance(value, bytes):
        text = value.hex()
        return "0x" + text if len(text) <= 20 else "0x" + text[:12] + "…"
    return str(value)


def explain(evm, tx_hash: str) -> str:  # noqa: ANN001 - Evm client, kept loose
    """Replay a mined transaction one block earlier and decode its revert."""
    try:
        tx = evm.call("eth_getTransactionByHash", [tx_hash])
    except Exception:
        return ""
    if not tx or not tx.get("blockNumber"):
        return ""
    block = int(tx["blockNumber"], 16)
    payload = {"from": tx.get("from"), "to": tx["to"], "data": tx["input"], "value": tx.get("value", "0x0")}
    for block_param in (hex(block - 1), "latest"):
        try:
            evm.call("eth_call", [payload, block_param])
        except Exception as exc:  # noqa: BLE001
            error = getattr(exc, "error", None) or {}
            data = error.get("data") if isinstance(error, dict) else None
            if isinstance(data, dict):
                data = data.get("data")
            if data:
                return decode_revert_data(data)
    return ""
