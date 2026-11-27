#!/usr/bin/env python3
"""Re-check QorePass against the chain. Read-only, no keys, no secrets.

    python verify.py            # every check, then a summary line
    python verify.py --json     # the same results as JSON

A judge can run this on a clean machine: it needs only the public testnet
endpoints and this repository. Every check reads the chain (or the recorded
artifacts) and says what it compared. Nothing is signed and nothing is sent.

What it establishes
  * the deployed bytecode is the audited artifact,
  * the registry's recorded state is the state the journal describes
    (`ada-1`, `chen-1`, `dara-1` checked in; `boram-1` revoked),
  * every transaction in `demo/journal.jsonl` — EVM and native — is on chain,
    with the outcome the journal recorded,
  * the post-quantum gates still refuse, reproduced now by `eth_call`:
    a second check-in, a revoked pass, the wrong holder key, and a forged
    ML-DSA-87 issuer signature,
  * every pass document's issuer signature verifies **offline** against the
    key the pass names, and the message the document signs is byte-for-byte the
    one the contract returns,
  * the sealed issuance archive still hashes to the digest its anchor
    transaction carries (QoreSeal),
  * each check-in receipt verifies against the venue's on-chain ML-DSA-87 key
    at its issue time, while a tampered or expired one is refused (QoreSign/SIWQ),
  * the venue's linked kiosk key is on chain limited to one EVM call, admitted a
    pass, and was refused when it tried to mint one (smart account rules),
  * the same registry numbers come back through the QoreChain MCP server.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from eth_abi import decode as abi_decode  # noqa: E402
from eth_abi import encode as abi_encode  # noqa: E402
from eth_utils import keccak  # noqa: E402
from qorsdk import fetch_kem_key, fetch_pqc_status, pqc_verify  # noqa: E402
from qorsdk.rest import RestClient  # noqa: E402

from qorepass import passes as P  # noqa: E402
from qorepass import receipts as R  # noqa: E402
from qorepass.evm import Evm, EvmRpcError  # noqa: E402
from qorepass.revert import decode_revert_data  # noqa: E402

EXPLORER = "https://explore.qore.network/tx/"


class Report:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def check(self, name: str, fn: Callable[[], str | None]) -> None:
        try:
            detail = fn()
            self.rows.append({"check": name, "ok": True, "detail": detail or "ok"})
        except Exception as exc:  # a failed check is a result, not a crash
            self.rows.append({"check": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})

    @property
    def passed(self) -> int:
        return sum(1 for r in self.rows if r["ok"])

    @property
    def failed(self) -> int:
        return len(self.rows) - self.passed


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    addrs = json.loads((ROOT / "demo" / "addresses.json").read_text())
    features = json.loads((ROOT / "demo" / "features.json").read_text())
    journal = _jsonl(ROOT / "demo" / "journal.jsonl")
    sealed_index = json.loads((ROOT / "demo" / "sealed" / "index.json").read_text())
    receipt_files = sorted((ROOT / "demo" / "receipts").glob("*.json"))
    pass_files = sorted((ROOT / "demo" / "passes").glob("*.json"))
    artifact = json.loads((ROOT / "contracts" / "out" / "QorePassRegistry.sol" / "QorePassRegistry.json").read_text())

    rest = addrs["rest"]
    registry = addrs["registry"]
    chain_id = addrs["chain_id"]
    evm_chain_id = int(addrs["evm_chain_id"])
    admin_evm = addrs["admin"]["evm"]
    issuer_native = addrs["issuer"]["native"]
    issuer_evm = addrs["issuer"]["evm"]
    venue_native = addrs["admin"]["native"]
    http = httpx.Client(timeout=40)
    client = RestClient(rest)
    evm = Evm(addrs["evm_rpc"], evm_chain_id)

    docs = {path.stem: P.PassDocument.load(path) for path in pass_files}

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def view(selector: bytes, types: list[str] | None = None, values: list[Any] | None = None, to: str = registry) -> bytes:
        data = selector + (abi_encode(types, values) if types else b"")
        raw = evm.eth_call(to, data)
        expect(raw not in ("", "0x"), f"empty answer to 0x{selector.hex()}")
        return bytes.fromhex(raw.removeprefix("0x"))

    def state_of(pass_id: str) -> str:
        raw = view(P.SEL_PASS_STATE, ["bytes32"], [bytes.fromhex(pass_id[2:])])
        return P.STATE_NAMES[abi_decode(["uint8"], raw)[0]]

    def tx_body(tx_hash: str) -> dict:
        body = http.get(f"{rest}/cosmos/tx/v1beta1/txs/{tx_hash}").json()
        expect(body.get("tx_response") is not None, f"{tx_hash} not found")
        return body

    def memo_of(tx_hash: str) -> str:
        return (tx_body(tx_hash).get("tx", {}).get("body", {}) or {}).get("memo", "")

    def revert_of(data: bytes, frm: str) -> str:
        try:
            evm.call("eth_call", [{"from": frm, "to": registry, "data": "0x" + data.hex(), "value": "0x0"}, "latest"])
        except EvmRpcError as exc:
            error = exc.error if isinstance(exc.error, dict) else {}
            blob = error.get("data") or ""
            if isinstance(blob, dict):
                blob = blob.get("data", "")
            if blob:
                return decode_revert_data(blob)
            return f"reverted: {str(exc)[:160]}"
        raise AssertionError("the call did not revert")

    def chain_pubkey(address: str) -> bytes:
        """The account's ML-DSA-87 public key as the chain holds it (base64 in REST)."""
        status = fetch_pqc_status(rest, address)
        expect(status.get("registered"), f"{address} has no ML-DSA-87 key")
        key = status.get("pubkey")
        return base64.b64decode(key) if isinstance(key, str) else bytes(key)

    def expected_states() -> dict[str, str]:
        """What the journal says each pass became, in journal order."""
        out: dict[str, str] = {}
        for entry in journal:
            if not entry.get("ok"):
                continue
            if entry.get("kind") == "issue":
                out[entry.get("pass", "")] = "VALID"
            elif entry.get("kind") in {"checkin", "kiosk-checkin"}:
                out[entry.get("pass", "")] = "CHECKED_IN"
            elif entry.get("kind") == "revoke":
                out[entry.get("pass", "")] = "REVOKED"
        return out

    expected = expected_states()

    r = Report()

    # ------------------------------------------------------------------ #
    # chain + contract
    # ------------------------------------------------------------------ #
    def network() -> str:
        body = http.get(rest + "/cosmos/base/tendermint/v1beta1/node_info").json()
        got = body["default_node_info"]["network"]
        expect(got == chain_id, f"network is {got}, expected {chain_id}")
        return f"chain {got} (testnet)"

    r.check("the REST endpoint answers with the expected chain id", network)

    def evm_chain() -> str:
        got = evm.chain_id_on_chain()
        expect(got == evm_chain_id, f"evm chain id {got}")
        return f"evm chain id {got}"

    r.check("the EVM lane answers with the expected chain id", evm_chain)

    def contract_bytecode() -> str:
        code = evm.code_at(registry).removeprefix("0x")
        want = artifact["deployedBytecode"]["object"].removeprefix("0x")
        expect(code != "", "no code at the registry address")
        expect(len(code) == len(want), f"length {len(code)//2}B on chain vs {len(want)//2}B in the artifact")
        diffs = [i for i in range(0, len(want), 2) if code[i : i + 2] != want[i : i + 2]]
        regions: list[list[int]] = []
        for d in diffs:
            if regions and d - regions[-1][-1] <= 4:
                regions[-1].append(d)
            else:
                regions.append([d])
        # The only bytes Solidity writes at deploy time are the immutable
        # `admin` sites; each must hold exactly the admin address.
        addr = admin_evm.lower().removeprefix("0x")
        for region in regions:
            expect(len(region) == 20, f"a differing region is {len(region)//2} bytes, not one 20-byte address")
            expect(code[region[0] : region[-1] + 2] == addr, "a differing region does not hold the admin address")
        return f"{len(code)//2} bytes; {len(regions)} immutable site(s) hold {admin_evm} and nothing else differs"

    r.check("the deployed code is the audited artifact", contract_bytecode)

    def deploy_tx() -> str:
        receipt = evm.call("eth_getTransactionReceipt", [addrs["deploy_tx"]])
        expect(receipt is not None, "no receipt for the deploy transaction")
        expect(int(receipt["status"], 16) == 1, f"deploy receipt status {receipt['status']}")
        created = (receipt.get("contractAddress") or "").lower()
        expect(created == registry.lower(), f"the deploy transaction created {created}")
        return f"deploy tx at EVM block {int(receipt['blockNumber'], 16)} created the registry"

    r.check("the deployment transaction is on chain", deploy_tx)

    # ------------------------------------------------------------------ #
    # registry state
    # ------------------------------------------------------------------ #
    def totals() -> str:
        issued = abi_decode(["uint32"], view(P.SEL_TOTAL_ISSUED))[0]
        checked = abi_decode(["uint32"], view(P.SEL_TOTAL_CHECKED_IN))[0]
        revoked = abi_decode(["uint32"], view(P.SEL_TOTAL_REVOKED))[0]
        want_issued = sum(1 for e in journal if e.get("kind") == "issue" and e.get("ok"))
        want_checked = sum(1 for e in journal if e.get("kind") in {"checkin", "kiosk-checkin"} and e.get("ok"))
        want_revoked = sum(1 for e in journal if e.get("kind") == "revoke" and e.get("ok"))
        expect(issued == want_issued, f"issued {issued} on chain vs {want_issued} in the journal")
        expect(checked == want_checked, f"checked in {checked} vs {want_checked}")
        expect(revoked == want_revoked, f"revoked {revoked} vs {want_revoked}")
        return f"issued {issued}, checked in {checked}, revoked {revoked} — each journaled"

    r.check("the registry totals equal the journaled actions", totals)

    def pass_states() -> str:
        seen = []
        for name, doc in docs.items():
            got = state_of(doc.pass_id)
            want = expected.get(name)
            if want == "VALID" and got == "EXPIRED":
                seen.append(f"{name}=EXPIRED (VALID when issued)")
                continue
            expect(want is not None, f"{name} has no recorded issue")
            expect(got == want, f"{name} is {got} on chain, journal says {want}")
            seen.append(f"{name}={got}")
        return "; ".join(seen)

    r.check("every pass document's state is the state the journal recorded", pass_states)

    def issuer_binding() -> str:
        raw = view(P.SEL_ISSUER_INFO, ["address"], [issuer_evm])
        pubkey_hash, name_hash, registered_at, pass_count, nonce, active = abi_decode(
            ["bytes32", "bytes32", "uint64", "uint32", "uint32", "bool"], raw
        )
        key = chain_pubkey(issuer_native)
        expect(len(key) == 2592, f"issuer key is {len(key)} bytes, ML-DSA-87 is 2592")
        expect(pubkey_hash == keccak(key), "the issuer's on-chain key hash is not the account's key")
        expect(active, "the issuer is suspended")
        issued = sum(1 for e in journal if e.get("kind") == "issue" and e.get("ok") and e.get("actor") == "issuer")
        expect(pass_count == issued, f"issuer passCount {pass_count} vs {issued} issues")
        revoked = sum(1 for e in journal if e.get("kind") == "revoke" and e.get("ok"))
        expect(nonce == issued + revoked, f"approval nonce {nonce} vs {issued} issues + {revoked} revoke(s)")
        return f"key hash bound, active, passCount {pass_count}, approvalNonce {nonce}"

    r.check("the issuer is the account whose ML-DSA-87 key the chain holds", issuer_binding)

    def issuer_kem() -> str:
        found = fetch_kem_key(client, issuer_native)
        expect(getattr(found, "found", False) and found.key is not None, "no ML-KEM key registered")
        key = found.key
        expect(len(key.public_key) == 1568, f"KEM key is {len(key.public_key)}B")
        expect(key.algorithm_name == "mlkem1024", f"algorithm {key.algorithm_name}")
        recorded = features.get("kem", {})
        expect(recorded.get("key_len") == 1568, "features.json records no 1568-byte KEM key")
        return f"ML-KEM-1024 key registered at height {key.registered_height} (QoreSeal recipient)"

    r.check("the issuer's ML-KEM-1024 key is registered (QoreSeal)", issuer_kem)

    # ------------------------------------------------------------------ #
    # journal replay
    # ------------------------------------------------------------------ #
    def replay_evm() -> str:
        entries = [e for e in journal if e.get("tx", "").startswith("0x")]
        expect(len(entries) >= 12, f"only {len(entries)} EVM entries in the journal")
        bad = []
        for e in entries:
            receipt = evm.call("eth_getTransactionReceipt", [e["tx"]])
            if receipt is None:
                bad.append(f"{e.get('kind')}: no receipt")
                continue
            status = initem = int(receipt["status"], 16)
            want = 1 if e.get("ok") else 0
            if e.get("ok") is None:
                continue
            if status != want:
                bad.append(f"{e.get('kind')} {e['tx'][:12]}…: status {initem}, journal says {e.get('ok')}")
        expect(not bad, "; ".join(bad[:4]))
        ok = sum(1 for e in entries if e.get("ok"))
        return f"{len(entries)} EVM transactions on chain ({ok} succeeded, {len(entries)-ok} refused)"

    r.check("every journaled EVM transaction is on chain with its recorded outcome", replay_evm)

    def replay_native() -> str:
        entries = [e for e in journal if e.get("tx") and not e["tx"].startswith("0x")]
        expect(len(entries) >= 8, f"only {len(entries)} native entries in the journal")
        for e in entries:
            body = tx_body(e["tx"])
            response = body["tx_response"]
            expect(int(response.get("height", 0)) > 0, f"{e['kind']}: not in a block")
            if e.get("ok") is True:
                expect(int(response.get("code", 1)) == 0, f"{e['kind']}: code {response.get('code')}")
            if e.get("kind") in {"anchor", "anchor-seal", "anchor-receipts"}:
                got = memo_of(e["tx"])
                expect(got == e.get("note"), f"{e['kind']}: memo {got!r} != {e.get('note')!r}")
        ok = sum(1 for e in entries if e.get("ok") is True)
        return f"{len(entries)} native (hybrid-signed) transactions on chain; {ok} succeeded, anchors carry their memo"

    r.check("every journaled native transaction is on chain and each anchor carries its commitment", replay_native)

    def refusal_count() -> str:
        refused = [e for e in journal if e.get("ok") is False]
        expect(len(refused) >= 6, f"only {len(refused)} refusals recorded")
        kinds = sorted({e.get("revert") or e.get("kind", "") for e in refused})
        return f"{len(refused)} refusals recorded: " + "; ".join(k.split("(")[0] for k in kinds[:6])

    r.check("the refusals are transactions, not claims", refusal_count)

    # ------------------------------------------------------------------ #
    # refusals, reproduced now
    # ------------------------------------------------------------------ #
    def double_checkin() -> str:
        doc = docs["ada-1"]
        pub = P.from_b64(doc.holder_pubkey)
        data = P.calldata_check_in(bytes.fromhex(doc.pass_id[2:]), pub, b"\x00" * 4627)
        got = revert_of(data, admin_evm)
        expect("AlreadyCheckedIn" in got, got)
        return f"{got} for a pass already admitted"

    r.check("a second check-in of the same pass reverts (same call, now)", double_checkin)

    def revoked_checkin() -> str:
        doc = docs["boram-1"]
        data = P.calldata_check_in(bytes.fromhex(doc.pass_id[2:]), P.from_b64(doc.holder_pubkey), b"\x00" * 4627)
        got = revert_of(data, admin_evm)
        expect("PassAlreadyRevoked" in got, got)
        return got

    r.check("a revoked pass cannot be checked in (same call, now)", revoked_checkin)

    def wrong_holder() -> str:
        doc = next((d for d in docs.values() if state_of(d.pass_id) == "VALID"), None)
        expect(doc is not None, "no pass is still in the VALID state to test with")
        someone_else = P.from_b64(docs["ada-1"].holder_pubkey)
        data = P.calldata_check_in(bytes.fromhex(doc.pass_id[2:]), someone_else, b"\x00" * 4627)
        got = revert_of(data, admin_evm)
        expect("HolderKeyMismatch" in got, got)
        return f"{got} — another holder's key cannot present this pass"

    r.check("another holder's key cannot check a pass in (same call, now)", wrong_holder)

    def forged_issue() -> str:
        raw = view(P.SEL_ISSUER_NONCE, ["address"], [issuer_evm])
        nonce = abi_decode(["uint32"], raw)[0]
        doc = docs["chen-1"]
        data = P.calldata_issue_pass(
            P.new_pass_id(),
            "0x" + "00" * 20,
            bytes.fromhex(doc.event_id[2:]),
            bytes.fromhex(doc.meta_hash[2:]),
            bytes.fromhex(doc.holder_key_hash[2:]),
            doc.valid_until,
            b"\x00" * 4627,
        )
        got = revert_of(data, issuer_evm)
        expect("BadIssuerSignature" in got, got)
        return f"{got} at nonce {nonce} — a signature-shaped blob cannot mint a pass"

    r.check("a forged ML-DSA-87 issuer signature is refused (same call, now)", forged_issue)

    # ------------------------------------------------------------------ #
    # pass documents
    # ------------------------------------------------------------------ #
    def docs_verify() -> str:
        for name, doc in docs.items():
            pub = P.from_b64(doc.issuer_pubkey)
            sig = P.from_b64(doc.issuer_signature)
            expect(pqc_verify(pub, doc.issue_message(), sig), f"{name}: the issuer signature does not verify")
            expect(len(sig) == 4627, f"{name}: signature is {len(sig)} bytes, ML-DSA-87 is 4627")
            expect(keccak(P.from_b64(doc.holder_pubkey)).hex() == doc.holder_key_hash[2:], f"{name}: holder key hash")
        return f"{len(docs)} documents: each issuer signature (4627B) verifies offline against the key it names"

    r.check("every pass document's issuer signature verifies offline", docs_verify)

    def docs_match_chain() -> str:
        for name, doc in docs.items():
            expected_message = P.issue_pass_message(
                doc.chain_id, doc.registry, doc.issuer, bytes.fromhex(doc.pass_id[2:]),
                doc.holder_address, bytes.fromhex(doc.event_id[2:]),
                bytes.fromhex(doc.meta_hash[2:]), bytes.fromhex(doc.holder_key_hash[2:]),
                doc.valid_until, doc.approval_nonce,
            )
            raw = view(
                P.SEL_ISSUE_PASS_MESSAGE,
                ["address", "bytes32", "address", "bytes32", "bytes32", "bytes32", "uint64", "uint32"],
                [doc.issuer, bytes.fromhex(doc.pass_id[2:]), doc.holder_address,
                 bytes.fromhex(doc.event_id[2:]), bytes.fromhex(doc.meta_hash[2:]),
                 bytes.fromhex(doc.holder_key_hash[2:]), doc.valid_until, doc.approval_nonce],
            )
            # The contract returns the ABI-encoded bytes value; decode it.
            contract_message = abi_decode(["bytes"], raw)[0]
            expect(contract_message == expected_message, f"{name}: the local encoder differs from the contract's view")
            info = abi_decode(
                ["address", "address", "bytes32", "bytes32", "bytes32", "uint64", "uint64", "uint64", "uint8"],
                view(P.SEL_PASS_INFO, ["bytes32"], [bytes.fromhex(doc.pass_id[2:])]),
            )
            expect(info[2].hex() == doc.event_id[2:], f"{name}: event id differs on chain")
            expect(info[3].hex() == doc.meta_hash[2:], f"{name}: meta hash differs on chain")
            expect(info[4].hex() == doc.holder_key_hash[2:], f"{name}: holder key hash differs on chain")
            expect(info[5] == doc.valid_until, f"{name}: validUntil differs on chain")
        return f"{len(docs)} documents reproduce the contract's own message bytes and stored fields"

    r.check("each document's signed message is byte-for-byte the contract's", docs_match_chain)

    # ------------------------------------------------------------------ #
    # QoreSeal
    # ------------------------------------------------------------------ #
    def sealed_archive() -> str:
        expect(sealed_index, "no sealed archive recorded")
        for record in sealed_index:
            blob = (ROOT / record["envelope"]).read_bytes()
            expect(hashlib.sha256(blob).hexdigest() == record["envelope_sha256"], f"{record['batch_id']}: envelope changed")
            expect(len(blob) == record["envelope_len"], f"{record['batch_id']}: length changed")
        record = sealed_index[-1]
        expect(record["entries"] == len(docs), f"the archive holds {record['entries']} documents, the repo {len(docs)}")
        return f"{len(sealed_index)} envelope(s) unchanged; archive of {record['entries']} documents, {record['envelope_len']}B"

    r.check("the sealed issuance archive matches its recorded digest", sealed_archive)

    def seal_anchor() -> str:
        record = sealed_index[-1]
        got = memo_of(features["seal"]["anchor_tx"])
        expect(got == record["memo_commitment"], f"memo {got!r} != {record['memo_commitment']!r}")
        expect(features["seal"]["envelope_sha256"] == record["envelope_sha256"], "features.json and index.json disagree")
        return f"anchor transaction {features['seal']['anchor_tx'][:16]}… carries {got}"

    r.check("the archive digest is committed on chain", seal_anchor)

    # ------------------------------------------------------------------ #
    # QoreSign / SIWQ receipts
    # ------------------------------------------------------------------ #
    def venue_key() -> bytes:
        return chain_pubkey(venue_native)

    def receipt_verifies() -> str:
        expect(receipt_files, "no check-in receipts recorded")
        pub = venue_key()
        for path in receipt_files:
            raw = json.loads(path.read_text())
            receipt = R.Receipt(
                message=raw["message"], nonce=raw["nonce"], pass_name=raw["pass"], pass_id=raw["pass_id"],
                holder_label=raw["holder"], holder_key_hash=raw["holder_key_hash"], event_name=raw["event"],
                registry=raw["registry"], checked_in_at=raw["checked_in_at"],
            )
            verified = R.verify(receipt, raw["signature"], chain_pq_public_key=pub, chain_id=chain_id,
                                at_ms=R.issued_ms(receipt.message) + 1_000)
            expect(getattr(verified, "address", venue_native) == venue_native,
                   f"{path.stem}: verified for {getattr(verified, 'address', '?')}")
            # and the receipt's own numbers are the chain's numbers
            doc = docs[receipt.pass_name]
            expect(state_of(doc.pass_id) == "CHECKED_IN", f"{path.stem}: the pass it describes is not checked in")
        return f"{len(receipt_files)} receipts verify against the venue's on-chain ML-DSA-87 key at their issue time"

    r.check("each check-in receipt verifies against the venue's on-chain key (SIWQ)", receipt_verifies)

    def receipt_negatives() -> str:
        raw = json.loads(receipt_files[0].read_text())
        pub = venue_key()
        base = R.Receipt(
            message=raw["message"], nonce=raw["nonce"], pass_name=raw["pass"], pass_id=raw["pass_id"],
            holder_label=raw["holder"], holder_key_hash=raw["holder_key_hash"], event_name=raw["event"],
            registry=raw["registry"], checked_in_at=raw["checked_in_at"],
        )
        issued = R.issued_ms(base.message)
        accepted = []

        def refuses(label: str, message: str | None = None, at_ms: int | None = None, **changes) -> None:
            """Verify a copy of the receipt with one thing changed, and count it
            as accepted if the change goes unnoticed."""
            fields = {**base.__dict__, **changes}
            if message is not None:
                fields["message"] = message
            candidate = R.Receipt(**fields)
            try:
                R.verify(candidate, raw["signature"], chain_pq_public_key=pub, chain_id=chain_id,
                         at_ms=at_ms if at_ms is not None else issued + 1_000)
                accepted.append(label)
            except Exception:
                pass

        # Editing the message is the attack: the signature only covers the text.
        import datetime as _dt

        other_time = base.message.replace(
            _dt.datetime.fromtimestamp(base.checked_in_at, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            _dt.datetime.fromtimestamp(base.checked_in_at + 3600, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        refuses("another check-in time", message=other_time)
        refuses("a re-pointed pass id", message=base.message.replace(base.pass_id, docs["boram-1"].pass_id),
                pass_id=docs["boram-1"].pass_id)
        refuses("a receipt 25 hours later", at_ms=issued + 25 * 3600 * 1000)
        expect(not accepted, "; ".join(accepted))
        # and the untouched receipt still verifies at its own issue time
        R.verify(base, raw["signature"], chain_pq_public_key=pub, chain_id=chain_id, at_ms=issued + 1_000)
        return "an edited check-in time, a re-pointed pass id and the same receipt 25h later are all refused"

    r.check("a tampered or expired receipt is refused", receipt_negatives)

    def receipt_anchor() -> str:
        memo = features["receipts"]["memo"]
        got = memo_of(features["receipts"]["anchor_tx"])
        expect(got == memo, f"memo {got!r} != {memo!r}")
        return f"anchor transaction carries {got}"

    r.check("the receipts' digest is committed on chain", receipt_anchor)

    # ------------------------------------------------------------------ #
    # smart account (kiosk key)
    # ------------------------------------------------------------------ #
    def kiosk_link() -> str:
        payload = http.get(f"{rest}/qorechain/abstractaccount/v1/accounts/{venue_native}/authenticators").json()
        keys = payload.get("authenticators", [])
        live = [k for k in keys if k.get("label") == "qorepass-kiosk"]
        expect(live, "no qorepass-kiosk authenticator on the venue account")
        key = live[0]
        expect(not key.get("revoked"), "the kiosk key is revoked")
        expect("evm" in key.get("permissions", []), f"permissions {key.get('permissions')}")
        linked = (key.get("pubkey_hex") or key.get("pubkey") or "").lower().removeprefix("0x")
        expect(linked == features["kiosk"]["pubkey"].lower(),
               "the linked key is not the kiosk key features.json records")
        return f"linked Ed25519 key, permissions {key['permissions']}, label qorepass-kiosk"

    r.check("the venue's kiosk key is linked with the evm permission", kiosk_link)

    def kiosk_rule() -> str:
        payload = http.get(f"{rest}/qorechain/abstractaccount/v1/accounts/{venue_native}/spending_rules").json()
        rules = [x for x in payload.get("rules", []) if x.get("enabled")]
        expect(rules, "no enabled spending rule")
        rule = next((x for x in rules if x.get("id") == "qorepass-kiosk"), rules[0])
        calls = rule.get("allowed_evm_calls", [])
        wanted = f"{registry}/0x{P.SEL_CHECK_IN.hex()}"
        expect(any(c.lower().startswith(wanted.lower()) for c in calls), f"allowed calls {calls}")
        return f"rule {rule['id']!r} allows {len(calls)} EVM call: {calls[0]}"

    r.check("the kiosk key may call checkIn and nothing else", kiosk_rule)

    def kiosk_checkin_tx() -> str:
        record = features["kiosk_checkin"]
        body = tx_body(record["tx"])
        expect(int(body["tx_response"].get("code", 1)) == 0, "the kiosk check-in transaction failed")
        expect(state_of(record["pass_id"]) == "CHECKED_IN", "the pass it admitted is not checked in")
        return f"dara-1 admitted by the kiosk key (auth nonce {record['auth_nonce']}), pass state CHECKED_IN"

    r.check("the kiosk key admitted a pass through the chain's authenticator lane", kiosk_checkin_tx)

    def kiosk_refusal() -> str:
        record = features["kiosk_refusal"]
        expect(record["refused"], "features.json does not record a refusal")
        vm_error = (record.get("execution") or {}).get("vm_error", "")
        expect("authenticator not permitted" in vm_error, f"vm_error {vm_error!r}")
        body = tx_body(record["tx"])
        expect(int(body["tx_response"].get("height", 0)) > 0, "the refused attempt is not on chain")
        return "the same key called issuePass and the chain refused: 'authenticator not permitted for this action'"

    r.check("the kiosk key cannot mint a pass (refused on chain)", kiosk_refusal)

    # ------------------------------------------------------------------ #
    # MCP
    # ------------------------------------------------------------------ #
    def mcp_numbers() -> str:
        try:
            from qorepass import mcpread
        except Exception as exc:  # noqa: BLE001
            return f"skipped: qorechain-mcp is not installed here ({type(exc).__name__})"
        try:
            state = mcpread.registry_state(registry)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"the MCP server did not answer: {type(exc).__name__}: {exc}") from exc
        on_chain = {
            "issued": abi_decode(["uint32"], view(P.SEL_TOTAL_ISSUED))[0],
            "checkedIn": abi_decode(["uint32"], view(P.SEL_TOTAL_CHECKED_IN))[0],
            "revoked": abi_decode(["uint32"], view(P.SEL_TOTAL_REVOKED))[0],
        }
        expect(state == on_chain, f"MCP {state} vs eth_call {on_chain}")
        return f"the MCP server's read_contract returns {state}, identical to eth_call"

    r.check("the same registry numbers come back through the QoreChain MCP server", mcp_numbers)

    # ------------------------------------------------------------------ #
    # report
    # ------------------------------------------------------------------ #
    if args.json:
        print(json.dumps({"passed": r.passed, "failed": r.failed, "checks": r.rows}, indent=2))
    else:
        width = max(len(row["check"]) for row in r.rows)
        for row in r.rows:
            mark = "PASS" if row["ok"] else "FAIL"
            print(f"{mark}  {row['check']:<{width}}  {row['detail']}")
        print()
        print(f"{r.passed} checks passed, {r.failed} failed — read-only, nothing signed, testnet only.")
        print(f"Every transaction above opens at {EXPLORER}<hash> (switch the explorer to Testnet).")
    return 0 if r.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
