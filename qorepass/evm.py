"""Minimal EVM-lane client for QoreChain.

QoreChain's EVM lane admits a transaction only from an account that has a
registered ML-DSA-87 key **and** an open, unexhausted EVM window (opened on the
native lane with a hybrid signature). Once those two conditions hold, the EVM
lane behaves like Ethereum: nonce, gas price, `eth_call`, receipts.

This module deliberately keeps nonces chain-sourced: opening a window advances
the account sequence, which is also the EVM nonce, so a cached nonce is wrong
by construction.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
from eth_account import Account
from eth_utils import to_checksum_address

from .config import WEI_PER_UQOR  # noqa: F401  (re-exported for callers)


class EvmRpcError(RuntimeError):
    def __init__(self, method: str, error: Any) -> None:
        super().__init__(f"{method} failed: {json.dumps(error)[:600]}")
        self.error = error


@dataclass
class Receipt:
    tx_hash: str
    status: int
    gas_used: int
    block_number: int
    logs: list[dict]
    contract_address: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == 1


class Evm:
    def __init__(self, rpc_url: str, chain_id: int) -> None:
        self.url = rpc_url
        self.chain_id = chain_id
        self._http = httpx.Client(timeout=45.0)
        self._id = 0

    # ------------------------------------------------------------------ #
    # JSON-RPC
    # ------------------------------------------------------------------ #
    def call(self, method: str, params: list[Any] | None = None) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or []}
        response = self._http.post(self.url, json=payload)
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise EvmRpcError(method, body["error"])
        return body.get("result")

    def chain_id_on_chain(self) -> int:
        return int(self.call("eth_chainId"), 16)

    def gas_price(self) -> int:
        return int(self.call("eth_gasPrice"), 16)

    def nonce(self, address: str) -> int:
        return int(self.call("eth_getTransactionCount", [address, "pending"]), 16)

    def balance_wei(self, address: str) -> int:
        return int(self.call("eth_getBalance", [address, "latest"]), 16)

    def code_at(self, address: str) -> str:
        return self.call("eth_getCode", [address, "latest"])

    def eth_call(self, to: str, data: bytes | str, *, block: str = "latest") -> str:
        blob = "0x" + data.hex() if isinstance(data, bytes) else data
        return self.call("eth_call", [{"to": to, "data": blob, "value": "0x0"}, block])

    def block_number(self) -> int:
        return int(self.call("eth_blockNumber"), 16)

    # ------------------------------------------------------------------ #
    # Transactions
    # ------------------------------------------------------------------ #
    def send(
        self,
        private_key: bytes,
        *,
        to: str | None,
        data: bytes = b"",
        value_wei: int = 0,
        gas: int = 900_000,
        gas_price: int | None = None,
        nonce: int | None = None,
    ) -> str:
        sender = Account.from_key(private_key).address
        nonce = self.nonce(sender) if nonce is None else nonce
        tx = {
            "nonce": nonce,
            "gasPrice": gas_price if gas_price is not None else self.gas_price(),
            "gas": gas,
            "value": value_wei,
            "data": data,
            "chainId": self.chain_id,
        }
        if to is not None:
            tx["to"] = to_checksum_address(to)
        signed = Account.sign_transaction(tx, private_key)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        return self.call("eth_sendRawTransaction", ["0x" + raw.hex()])

    def deploy(
        self,
        private_key: bytes,
        artifact_path: str,
        constructor_types: list[str],
        constructor_args: list[Any],
        *,
        gas: int = 4_000_000,
        gas_price: int | None = None,
    ) -> str:
        from eth_abi import encode as abi_encode

        artifact = json.loads(open(artifact_path).read())
        bytecode = artifact["bytecode"]["object"]
        data = bytes.fromhex(bytecode[2:] if bytecode.startswith("0x") else bytecode)
        if constructor_types:
            data += abi_encode(constructor_types, constructor_args)
        return self.send(private_key, to=None, data=data, gas=gas, gas_price=gas_price)

    def wait(self, tx_hash: str, timeout: float = 120.0) -> Receipt:
        deadline = time.time() + timeout
        while time.time() < deadline:
            rec = self.call("eth_getTransactionReceipt", [tx_hash])
            if rec:
                return Receipt(
                    tx_hash=tx_hash,
                    status=int(rec["status"], 16),
                    gas_used=int(rec["gasUsed"], 16),
                    block_number=int(rec["blockNumber"], 16),
                    logs=rec.get("logs", []),
                    contract_address=rec.get("contractAddress"),
                )
            time.sleep(1.5)
        raise TimeoutError(f"no receipt for {tx_hash} after {timeout}s")
