"""Native lane: post-quantum key registration, hybrid signatures, EVM windows.

A QoreChain native transaction carries a classical signature *and* an
ML-DSA-87 signature (the `PQCHybridSignature` extension). The EVM lane is
reachable only through a window opened by such a transaction, so the
quantum-resistant signature is the gate to every EVM call this project makes.

Only testnet. All keys are throwaway.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from qorsdk import decode_execution_results, decode_tx_error, fetch_pqc_status
from qorsdk.key_integrity import should_attach_proof_of_possession, sign_proof_of_possession
from qorsdk.messages import msg as compose
from qorsdk.sign_eth import sign_classical_eth, sign_hybrid_eth
from qorsdk.tx import broadcast, hybrid_sign_and_broadcast
from qorsdk.unified import UnifiedAccount

from .config import Settings


@dataclass
class TxOutcome:
    tx_hash: str
    code: int
    raw_log: str

    @property
    def ok(self) -> bool:
        return self.code == 0


class Chain:
    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self._http = httpx.Client(timeout=45.0)

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        response = self._http.get(self.cfg.rest + path, params=params)
        response.raise_for_status()
        return response.json()

    def account_state(self, address: str) -> tuple[int, int]:
        """(account_number, sequence)."""
        data = self.get(f"/cosmos/auth/v1beta1/accounts/{address}")
        acct = data["account"]
        base = acct.get("base_account") or acct.get("base_vesting_account", {}).get("base_account") or acct
        return int(base["account_number"]), int(base["sequence"])

    def balances(self, address: str) -> dict[str, int]:
        data = self.get(f"/cosmos/bank/v1beta1/balances/{address}")
        return {coin["denom"]: int(coin["amount"]) for coin in data.get("balances", [])}

    def uqor(self, address: str) -> int:
        return self.balances(address).get("uqor", 0)

    def pqc_status(self, address: str) -> dict:
        status = fetch_pqc_status(self.cfg.rest, address)
        pubkey = status.get("pubkey", b"")
        if isinstance(pubkey, str):
            import base64

            try:
                pubkey = base64.b64decode(pubkey)
            except Exception:
                pubkey = b""
        return {
            "registered": bool(status.get("registered", False)),
            "pubkey": pubkey or b"",
            "possession_proven": status.get("possession_proven"),
        }

    def tx(self, tx_hash: str) -> dict:
        return self.get(f"/cosmos/tx/v1beta1/txs/{tx_hash}")

    def block_height(self) -> int:
        return int(self.get("/cosmos/base/tendermint/v1beta1/blocks/latest")["block"]["header"]["height"])

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def _fee(self, gas: int | None = None, fee_uqor: int | None = None) -> dict:
        gas = gas or self.cfg.gas
        fee_uqor = fee_uqor or self.cfg.fee_uqor
        return {"amount": [{"denom": "uqor", "amount": str(fee_uqor)}], "gas": str(gas)}

    def _outcome(self, response: dict) -> TxOutcome:
        txr = response.get("tx_response") or response
        code = int(txr.get("code", 0) or 0)
        raw_log = txr.get("raw_log", "") or ""
        if code != 0 and raw_log:
            try:
                raw_log = f"{raw_log} ({decode_tx_error(txr)})"
            except Exception:
                pass
        return TxOutcome(tx_hash=txr.get("txhash", ""), code=code, raw_log=raw_log[:700])

    def _settle(self, outcome: TxOutcome, timeout: float = 40.0) -> TxOutcome:
        """Wait for inclusion: `sync` broadcast may not carry the final code."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                body = self.tx(outcome.tx_hash)
            except Exception:
                time.sleep(1.5)
                continue
            txr = body.get("tx_response") or {}
            if not txr.get("height") or txr.get("height") == "0":
                time.sleep(1.5)
                continue
            code = int(txr.get("code", 0) or 0)
            return TxOutcome(tx_hash=outcome.tx_hash, code=code, raw_log=(txr.get("raw_log") or "")[:700])
        return outcome

    def register_pqc_key(self, account: UnifiedAccount, memo: str = "qorepass:register-pqc") -> dict:
        """Register the account's canonical ML-DSA-87 key (idempotent).

        This is the one native message the chain accepts with the classical key
        alone — a hybrid signature would need the very key being registered.
        """
        status = self.pqc_status(account.cosmos)
        if status["registered"]:
            return {"already_registered": True, "tx_hash": None}

        account_number, sequence = self.account_state(account.cosmos)
        fields: dict[str, Any] = {
            "sender": account.cosmos,
            "public_key": account.pqc.public_key,
            "algorithm_id": 1,
            "ecdsa_pubkey": account.public_key,
            "key_type": "hybrid",
        }
        attach = False
        try:
            attach = should_attach_proof_of_possession(self.cfg.chain_id, self.cfg.rest)
        except Exception:
            attach = False
        if attach:
            fields["proof_of_possession"] = sign_proof_of_possession(
                chain_id=self.cfg.chain_id, account=account.cosmos, keypair=account.pqc
            )

        message = compose.pqc.register_pqc_key_v2(**fields)
        built = sign_classical_eth(
            account,
            self.cfg.chain_id,
            account_number,
            [message],
            self._fee(),
            sequence,
            memo=memo,
        )
        outcome = self._outcome(broadcast(self.cfg.rest, built.tx_raw_bytes, mode="sync"))
        if not outcome.ok:
            raise RuntimeError(f"PQC registration refused: {outcome.raw_log}")
        outcome = self._settle(outcome)
        if not outcome.ok:
            raise RuntimeError(f"PQC registration failed on chain: {outcome.raw_log}")
        time.sleep(4)
        if not self.pqc_status(account.cosmos)["registered"]:
            raise RuntimeError("PQC key is still not visible after registration")
        return {"already_registered": False, "tx_hash": outcome.tx_hash, "proof_of_possession": attach}

    def send_hybrid(self, account: UnifiedAccount, messages: list[Any], memo: str = "") -> TxOutcome:
        account_number, sequence = self.account_state(account.cosmos)
        response = hybrid_sign_and_broadcast(
            lambda version: sign_hybrid_eth(
                account,
                self.cfg.chain_id,
                account_number,
                messages,
                self._fee(),
                sequence,
                memo=memo,
                sign_bytes_version=version,
            ),
            chain_id=self.cfg.chain_id,
            rest_url=self.cfg.rest,
            mode="sync",
        )
        outcome = self._outcome(response)
        if outcome.ok:
            outcome = self._settle(outcome)
        return outcome

    def send_uqor(self, sender: UnifiedAccount, to: str, amount_uqor: int, memo: str = "") -> TxOutcome:
        from qorsdk.messages.cosmos import MsgSend

        message = MsgSend(
            from_address=sender.cosmos,
            to_address=to,
            amount=[{"denom": "uqor", "amount": str(amount_uqor)}],
        )
        return self.send_hybrid(
            sender,
            [{"type_url": "/cosmos.bank.v1beta1.MsgSend", "value": message}],
            memo=memo,
        )

    def open_evm_window(
        self,
        account: UnifiedAccount,
        *,
        blocks: int,
        max_txs: int,
        max_value_uqor: int,
        targets: list[str] | None = None,
        memo: str = "qorepass:open-window",
    ) -> TxOutcome:
        message = compose.pqc.open_evm_window(
            sender=account.cosmos,
            blocks=blocks,
            max_txs=max_txs,
            max_value=max_value_uqor,
            native_only=False,
            allowed_targets=list(targets or ()),
        )
        return self.send_hybrid(account, [message], memo=memo)

    def evm_window(self, address: str) -> Any:
        from qorsdk import get_evm_window

        return get_evm_window(self, address)

    def execution_results(self, tx_hash: str) -> list[Any]:
        try:
            return decode_execution_results(self.tx(tx_hash))
        except Exception:
            return []
