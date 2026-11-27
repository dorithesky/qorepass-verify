"""The on-chain primitives QorePass added after the first submission.

    python scripts/onchain_features.py kem             # register the issuer's ML-KEM-1024 key (QoreSeal)
    python scripts/onchain_features.py seal            # seal the issuance archive (offline)
    python scripts/onchain_features.py anchor-seal     # commit the sealed digest in a hybrid tx
    python scripts/onchain_features.py receipts        # QoreSign SIWQ check-in receipts (offline)
    python scripts/onchain_features.py anchor-receipts # commit the receipts digest in a hybrid tx
    python scripts/onchain_features.py link-kiosk      # link the kiosk key, restricted to checkIn
    python scripts/onchain_features.py window          # reopen EVM windows (venue, issuer)
    python scripts/onchain_features.py kiosk-checkin   # check a pass in as the venue through the kiosk key
    python scripts/onchain_features.py show            # read every one of them back from the chain

Everything is a hybrid (classical + ML-DSA-87) native transaction from a
throwaway testnet account, or an EVM call inside a window opened by one. Nothing
here touches mainnet and nothing costs anything: test QOR only. Secrets stay in
`keys/`, which is gitignored.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import qoreseal  # noqa: E402
from qorsdk import fetch_kem_key, fetch_pqc_status  # noqa: E402
from qorsdk.rest import RestClient  # noqa: E402
from qorsdk.unified import derive_unified_account  # noqa: E402

from qorepass import kiosk, passes as P, receipts, sealing  # noqa: E402
from qorepass.chain import Chain  # noqa: E402
from qorepass.cli import Context, holder_keys, onchain_state, record  # noqa: E402
from qorepass.config import ROOT as REPO, settings  # noqa: E402

DEMO = REPO / "demo"
PASS_DIR = DEMO / "passes"
SEALED_DIR = DEMO / "sealed"
RECEIPT_DIR = DEMO / "receipts"
FEATURES = DEMO / "features.json"


def load_features() -> dict:
    return json.loads(FEATURES.read_text()) if FEATURES.exists() else {}


def save_features(data: dict) -> None:
    FEATURES.parent.mkdir(parents=True, exist_ok=True)
    FEATURES.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def say(label: str, **fields: object) -> None:
    parts = " ".join(f"{k}={v}" for k, v in fields.items() if v not in (None, ""))
    print(f"[{label}] {parts}" if parts else f"[{label}]")


def ctx() -> Context:
    return Context(settings())


# --------------------------------------------------------------------------- #
# QoreSeal — the ML-KEM key, then the archive
# --------------------------------------------------------------------------- #
def cmd_kem() -> dict:
    c = ctx()
    issuer = c.issuer
    keys = sealing.seal_keys(settings().issuer_mnemonic)
    rest = RestClient(settings().rest)

    already = fetch_kem_key(rest, issuer.cosmos)
    if already.found and already.key is not None:
        entry = {
            "address": issuer.cosmos,
            "tx": getattr(already.key, "tx_hash", "") or "",
            "already": True,
            "key_len": len(already.key.public_key),
            "chain_matches_derivation": already.key.public_key == keys.mlkem_public_key,
            "algorithm": already.key.algorithm_name,
            "registered_height": already.key.registered_height,
            "checked_at": int(time.time()),
        }
        data = load_features()
        data["kem"] = entry
        save_features(data)
        say("kem", **{k: entry[k] for k in ("address", "already", "key_len", "algorithm", "registered_height")})
        return entry

    from qorsdk.messages import msg as compose

    message = compose.pqc.register_kem_key(sender=issuer.cosmos, public_key=keys.mlkem_public_key)
    outcome = c.chain.send_hybrid(issuer, [message], memo="qorepass:register-kem-key")
    say("register-kem", tx=outcome.tx_hash, code=outcome.code, log=outcome.raw_log[:200])
    if not outcome.ok:
        raise SystemExit("KEM key registration refused")

    found = None
    for _ in range(12):
        time.sleep(2)
        got = fetch_kem_key(rest, issuer.cosmos)
        if got.found and got.key is not None:
            found = got.key
            break
    entry = {
        "address": issuer.cosmos,
        "tx": outcome.tx_hash,
        "already": False,
        "key_len": len(keys.mlkem_public_key),
        "chain_matches_derivation": bool(found and found.public_key == keys.mlkem_public_key),
        "algorithm": found.algorithm_name if found else None,
        "registered_height": found.registered_height if found else None,
        "checked_at": int(time.time()),
    }
    data = load_features()
    data["kem"] = entry
    save_features(data)
    record({"kind": "register-kem", "actor": "issuer", "tx": outcome.tx_hash, "ok": True,
            "note": f"ML-KEM-1024 key for QoreSeal, {len(keys.mlkem_public_key)}B"})
    say("kem", **{k: entry[k] for k in ("address", "already", "key_len", "algorithm", "registered_height")})
    return entry


def cmd_seal() -> dict:
    """Seal every pass document into one archive for the issuer's eyes only."""
    c = ctx()
    keys = sealing.seal_keys(settings().issuer_mnemonic)
    archive, entries = sealing.build_archive(PASS_DIR)
    batch = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    sealed = sealing.seal_archive(keys, f"issuance-{batch}", archive, entries, SEALED_DIR)
    index = [r for r in sealing.read_index(SEALED_DIR) if r["batch_id"] != sealed.batch_id]
    record_dict = sealed.as_dict()
    record_dict["envelope"] = str(sealed.path.relative_to(REPO))
    index.append(record_dict)
    (SEALED_DIR / sealing.INDEX).write_text(json.dumps(index, indent=2) + "\n")

    # Prove the envelope opens with the issuer's key and nothing else.
    opened = sealing.open_archive(keys, sealed, sealed.batch_id)
    if opened != archive:
        raise SystemExit("the sealed archive did not open to the same bytes")
    entry = {
        **sealed.as_dict(),
        "envelope": str(sealed.path.relative_to(REPO)),
        "opened_and_matched": True,
        "sealed_at": int(time.time()),
        "recipient": c.issuer.cosmos,
        "recipient_evm": c.issuer.evm,
    }
    data = load_features()
    data["seal"] = entry
    save_features(data)
    say("seal", batch=sealed.batch_id, entries=entries, bytes=sealed.envelope_len,
        sha256=sealed.envelope_sha256[:16] + "…", memo=sealed.memo)
    return entry


def cmd_anchor_seal() -> dict:
    c = ctx()
    data = load_features()
    seal = data.get("seal")
    if not seal:
        raise SystemExit("run `seal` first")
    outcome = c.chain.send_uqor(c.issuer, c.issuer.cosmos, 1, memo=seal["memo_commitment"])
    say("anchor-seal", tx=outcome.tx_hash, code=outcome.code, memo=seal["memo_commitment"])
    if not outcome.ok:
        raise SystemExit("anchor refused: " + outcome.raw_log[:300])
    seal["anchor_tx"] = outcome.tx_hash
    seal["anchored_at"] = int(time.time())
    data["seal"] = seal
    save_features(data)
    record({"kind": "anchor-seal", "actor": "issuer", "tx": outcome.tx_hash, "ok": True,
            "note": seal["memo_commitment"]})
    return seal


def cmd_anchor() -> dict:
    """The pass-document anchor the first run used (kept for a full replay)."""
    c = ctx()
    import hashlib

    digests = [hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(PASS_DIR.glob("*.json"))]
    root = hashlib.sha256("".join(digests).encode()).hexdigest()
    memo = f"qorepass:v1:{root}"
    organizer = c.organizer
    outcome = c.chain.send_uqor(organizer, organizer.cosmos, 1, memo=memo)
    say("anchor", tx=outcome.tx_hash, code=outcome.code, memo=memo, docs=len(digests))
    record({"kind": "anchor", "actor": "organizer", "tx": outcome.tx_hash, "ok": outcome.ok, "note": memo})
    return {"tx": outcome.tx_hash, "memo": memo}


# --------------------------------------------------------------------------- #
# QoreSign — admission receipts
# --------------------------------------------------------------------------- #
def _checked_in_passes() -> list[tuple[str, dict]]:
    out = []
    for path in sorted(PASS_DIR.glob("*.json")):
        doc = P.PassDocument.load(path)
        out.append((path.stem, doc))
    return out


def cmd_receipts() -> dict:
    c = ctx()
    cfg = settings()
    venue = c.organizer
    chain_pq = c.chain.pqc_status(venue.cosmos)["pubkey"]
    written = []
    for name, doc in _checked_in_passes():
        state = onchain_state(c, doc.registry, bytes.fromhex(doc.pass_id[2:]))
        if state["state_name"] != "CHECKED_IN":
            continue
        receipt = receipts.build_receipt(
            account=venue.cosmos,
            chain_id=cfg.chain_id,
            pass_name=name,
            pass_id=doc.pass_id,
            holder_label=doc.holder_label,
            holder_key_hash=doc.holder_key_hash,
            event_name=doc.event_name,
            registry=doc.registry,
            checked_in_at=state["checked_in_at"],
        )
        signature = receipts.sign(receipt, cfg.organizer_mnemonic, venue.cosmos)
        verified = receipts.verify(
            receipt, signature, chain_pq_public_key=chain_pq, chain_id=cfg.chain_id,
            at_ms=receipts.issued_ms(receipt.message) + 1_000,
        )
        path = RECEIPT_DIR / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "version": "qorepass/siwq-receipt/v1",
            "venue": venue.cosmos,
            "venue_evm": venue.evm,
            "domain": receipts.DOMAIN,
            **receipt.as_dict(),
            "signature": signature,
            "verified_against_chain_key": True,
            "checked_in_tx": state.get("checked_in_tx", ""),
        }, indent=2) + "\n")
        written.append({"pass": name, "file": str(path.relative_to(REPO)), "message": receipt.message})
        say("receipt", **{"pass": name, "nonce": receipt.nonce, "checkedInAt": state["checked_in_at"]})

    if not written:
        raise SystemExit("no checked-in pass to receipt")
    data = load_features()
    data["receipts"] = {
        "files": [w["file"] for w in written],
        "count": len(written),
        "venue": venue.cosmos,
        "issued_at": int(time.time()),
    }
    save_features(data)
    return {"receipts": written}


def cmd_anchor_receipts() -> dict:
    c = ctx()
    venue = c.organizer
    items = []
    for path in sorted(RECEIPT_DIR.glob("*.json")):
        raw = json.loads(path.read_text())
        items.append(receipts.Receipt(
            message=raw["message"], nonce=raw["nonce"], pass_name=raw["pass"], pass_id=raw["pass_id"],
            holder_label=raw["holder"], holder_key_hash=raw["holder_key_hash"], event_name=raw["event"],
            registry=raw["registry"], checked_in_at=raw["checked_in_at"],
        ))
    if not items:
        raise SystemExit("run `receipts` first")
    memo = receipts.memo(items)
    outcome = c.chain.send_uqor(venue, venue.cosmos, 1, memo=memo)
    say("anchor-receipts", tx=outcome.tx_hash, code=outcome.code, memo=memo)
    if not outcome.ok:
        raise SystemExit("anchor refused: " + outcome.raw_log[:300])
    data = load_features()
    data.setdefault("receipts", {})["anchor_tx"] = outcome.tx_hash
    data["receipts"]["memo"] = memo
    save_features(data)
    record({"kind": "anchor-receipts", "actor": "organizer", "tx": outcome.tx_hash, "ok": True, "note": memo})
    return {"tx": outcome.tx_hash, "memo": memo}


# --------------------------------------------------------------------------- #
# Smart account — the kiosk key, and a check-in through it
# --------------------------------------------------------------------------- #
def cmd_link_kiosk() -> dict:
    c = ctx()
    cfg = settings()
    venue = c.organizer
    key = kiosk.load_or_create_key()
    msgs = kiosk.link_messages(
        owner=venue.cosmos,
        chain_id=cfg.chain_id,
        key=key,
        registry=c.registry,
        days=30,
    )
    outcome = c.chain.send_hybrid(venue, msgs, memo="qorepass:link-kiosk")
    say("link-kiosk", tx=outcome.tx_hash, code=outcome.code, pubkey=kiosk.public_key(key).hex()[:32] + "…",
        log=outcome.raw_log[:200])
    if not outcome.ok:
        raise SystemExit("kiosk link refused")
    time.sleep(4)
    payload = c.chain.get(f"/qorechain/abstractaccount/v1/accounts/{venue.cosmos}/authenticators")
    keys = payload.get("authenticators", [])
    entry = {
        "tx": outcome.tx_hash,
        "pubkey": kiosk.public_key(key).hex(),
        "label": kiosk.LABEL,
        "permissions": list(kiosk.PERMISSIONS),
        "allowed_evm_calls": [f"{c.registry}/0x{P.SEL_CHECK_IN.hex()}"],
        "linked_at": int(time.time()),
        "chain_sees": [
            {"label": k.get("label"), "permissions": k.get("permissions"), "revoked": k.get("revoked")}
            for k in keys
        ],
    }
    data = load_features()
    data["kiosk"] = entry
    save_features(data)
    record({"kind": "link-kiosk", "actor": "organizer", "tx": outcome.tx_hash, "ok": True,
            "note": f"Ed25519 kiosk key linked, evm call limited to checkIn on {c.registry}"})
    return entry


def cmd_window() -> dict:
    c = ctx()
    out = {}
    registry = c.registry
    for name, account in (("organizer", c.organizer), ("issuer", c.issuer)):
        outcome = c.chain.open_evm_window(
            account, blocks=3000, max_txs=12, max_value_uqor=12 * 300_000, targets=[registry],
        )
        say("open-window", account=name, tx=outcome.tx_hash, code=outcome.code)
        if not outcome.ok:
            raise SystemExit(f"window for {name} refused: {outcome.raw_log[:300]}")
        record({"kind": "open-window", "actor": name, "tx": outcome.tx_hash,
                "note": f"blocks=3000 txs=12 targets=['{registry}']"})
        out[name] = outcome.tx_hash
        time.sleep(2)
    return out


def _issue(c: Context, holder: str, name: str, event: str = "QoreChain Demo Day", valid_days: float = 7) -> dict:
    """Issue one pass, so the kiosk has something real to admit."""
    from eth_abi import encode as abi_encode
    from qorsdk import pqc_sign

    cfg = settings()
    issuer = c.issuer
    registry = c.registry
    _, holder_pub = holder_keys(holder)
    event_id = P.event_id_for(event)
    metadata = {"holder": holder, "tier": "builder"}
    meta_hash = P.hash_metadata(metadata)
    key_hash = P.holder_key_hash(holder_pub)
    pass_id = P.new_pass_id()
    valid_until = P.now_ts() + int(valid_days * 86400)
    raw = c.evm.eth_call(registry, P.SEL_ISSUER_NONCE + abi_encode(["address"], [issuer.evm]))
    nonce = int(raw, 16) if raw and raw != "0x" else 0
    message = P.issue_pass_message(cfg.evm_chain_id, registry, issuer.evm, pass_id, "0x" + "00" * 20,
                                   event_id, meta_hash, key_hash, valid_until, nonce)
    signature = pqc_sign(issuer.pqc.secret_key, message)
    data = P.calldata_issue_pass(pass_id, "0x" + "00" * 20, event_id, meta_hash, key_hash, valid_until, signature)
    tx = c.evm.send(issuer.private_key, to=registry, data=data, gas=cfg.evm_gas_call,
                    gas_price=cfg.evm_gas_price_wei)
    receipt = c.evm.wait(tx)
    doc = P.PassDocument(
        pass_id="0x" + pass_id.hex(), event_id="0x" + event_id.hex(), event_name=event, issuer=issuer.evm,
        holder_label=holder, holder_pubkey=P.b64(holder_pub), holder_key_hash="0x" + key_hash.hex(),
        holder_address="0x" + "00" * 20, meta_hash="0x" + meta_hash.hex(), valid_until=valid_until,
        approval_nonce=nonce, issued_at=P.now_ts() if receipt.ok else 0,
        issuer_pubkey=P.b64(issuer.pqc.public_key), issuer_signature=P.b64(signature), registry=registry,
        chain_id=cfg.evm_chain_id, status="issued" if receipt.ok else "refused", tx=tx,
        extra={"metadata": metadata},
    )
    doc.save(PASS_DIR / f"{name}.json")
    say("issue", **{"pass": name, "passId": doc.pass_id[:14] + "…", "holder": holder,
                    "nonce": nonce, "tx": tx, "status": "ok" if receipt.ok else "REFUSED"})
    record({"kind": "issue", "actor": "issuer", "pass": name, "pass_id": doc.pass_id, "holder": holder,
            "tx": tx, "ok": receipt.ok, "note": f"{event} · nonce {nonce} · sig {len(signature)}B"})
    if not receipt.ok:
        raise SystemExit("issuePass reverted")
    return {"name": name, "pass_id": doc.pass_id, "tx": tx}


def cmd_kiosk_checkin(args: list[str]) -> dict:
    from qorsdk import pqc_sign

    c = ctx()
    cfg = settings()
    key = kiosk.load_or_create_key()

    if not (PASS_DIR / "dara-1.json").exists():
        # a new holder for this rail, so the kiosk admits a pass nobody has seen
        from qorsdk import generate_pqc_keypair

        pair = generate_pqc_keypair()
        (ROOT / "keys" / "holder-dara.key").write_text(pair.secret_key.hex() + "\n")
        (ROOT / "keys" / "holder-dara.key").chmod(0o600)
        (ROOT / "keys" / "holder-dara.pub").write_bytes(pair.public_key)
        _issue(c, "dara", "dara-1")

    doc = P.PassDocument.load(PASS_DIR / "dara-1.json")
    holder_secret, holder_pub = holder_keys("dara")
    pass_id = bytes.fromhex(doc.pass_id[2:])
    message = P.check_in_message(doc.chain_id, doc.registry, pass_id, bytes.fromhex(doc.holder_key_hash[2:]))
    holder_signature = pqc_sign(holder_secret, message)

    result = kiosk.check_in_through_kiosk(
        chain=c.chain, cfg=cfg, key=key, owner_account=c.organizer, relayer=c.funder,
        registry=doc.registry, pass_id=pass_id, holder_pubkey=holder_pub, holder_signature=holder_signature,
    )
    state = onchain_state(c, doc.registry, pass_id)
    say("kiosk-checkin", **{"pass": "dara-1", "tx": result["tx"], "code": result["code"],
                            "onchain": state["state_name"], "exec": result.get("execution")})
    record({"kind": "kiosk-checkin", "actor": "kiosk key (linked)", "pass": "dara-1", "tx": result["tx"],
            "ok": state["state_name"] == "CHECKED_IN",
            "note": f"MsgExecuteEVM signed by the linked Ed25519 key, relayer paid, state {state['state_name']}"})
    data = load_features()
    data["kiosk_checkin"] = {"pass": "dara-1", "pass_id": doc.pass_id, "tx": result["tx"],
                             "auth_digest": result["auth_digest"], "auth_nonce": result["auth_nonce"],
                             "state": state["state_name"], "checked_in_at": state["checked_in_at"]}
    save_features(data)
    if state["state_name"] != "CHECKED_IN":
        raise SystemExit(f"kiosk check-in did not land: {state['state_name']}")
    return data["kiosk_checkin"]


def cmd_issue(argv: list[str]) -> dict:
    """Issue one pass (a holder who has not been admitted yet, for the gate test)."""
    holder = argv[0] if argv else "eun"
    name = argv[1] if len(argv) > 1 else f"{holder}-1"
    c = ctx()
    from qorsdk import generate_pqc_keypair

    if not (ROOT / "keys" / f"holder-{holder}.pub").exists():
        pair = generate_pqc_keypair()
        (ROOT / "keys" / f"holder-{holder}.key").write_text(pair.secret_key.hex() + "\n")
        (ROOT / "keys" / f"holder-{holder}.key").chmod(0o600)
        (ROOT / "keys" / f"holder-{holder}.pub").write_bytes(pair.public_key)
    return _issue(c, holder, name)


def cmd_kiosk_refuse() -> dict:
    """The same kiosk key tries to mint a pass: the chain refuses the call."""
    from eth_abi import encode as abi_encode

    c = ctx()
    cfg = settings()
    key = kiosk.load_or_create_key()
    doc = P.PassDocument.load(PASS_DIR / "dara-1.json")
    # A syntactically valid issuePass call with an empty signature: if the chain
    # let the kiosk key through, the contract would answer BadIssuerSignature.
    data = P.SEL_ISSUE_PASS + abi_encode(
        ["bytes32", "address", "bytes32", "bytes32", "bytes32", "uint64", "bytes"],
        [P.new_pass_id(), "0x" + "00" * 20, bytes.fromhex(doc.event_id[2:]),
         bytes.fromhex(doc.meta_hash[2:]), bytes.fromhex(doc.holder_key_hash[2:]),
         doc.valid_until, b""],
    )
    result = kiosk.execute_authorised(
        chain=c.chain, cfg=cfg, key=key, owner_account=c.organizer, relayer=c.funder,
        to=doc.registry, data=data, memo="qorepass:kiosk-refuse-issuePass",
    )
    refused = result["code"] != 0 or not (result.get("execution") or {}).get("success", True)
    say("kiosk-refuse", tx=result["tx"], code=result["code"], refused=refused,
        log=(result["raw_log"] or "")[:180])
    record({"kind": "kiosk-refuse", "actor": "kiosk key (linked)", "tx": result["tx"], "ok": not refused,
            "note": "the kiosk key called issuePass — outside its allowed_evm_calls",
            "revert": (result["raw_log"] or "")[:240] or "execution refused"})
    data_out = load_features()
    data_out["kiosk_refusal"] = {
        "tx": result["tx"], "code": result["code"], "refused": refused,
        "raw_log": (result["raw_log"] or "")[:400],
        "execution": result.get("execution"), "attempted": "issuePass(bytes32,address,bytes32,bytes32,bytes32,uint64,bytes)",
    }
    save_features(data_out)
    if not refused:
        raise SystemExit("the chain let the kiosk key call issuePass — this is a bug")
    return data_out["kiosk_refusal"]


# --------------------------------------------------------------------------- #
# read back
# --------------------------------------------------------------------------- #
def cmd_show() -> None:
    c = ctx()
    cfg = settings()
    rest = RestClient(cfg.rest)
    issuer = c.issuer
    kem = fetch_kem_key(rest, issuer.cosmos)
    pqc = fetch_pqc_status(cfg.rest, issuer.cosmos)
    print(json.dumps({
        "registry": c.registry,
        "issuer": {"native": issuer.cosmos, "evm": issuer.evm,
                   "pqc_registered": bool(pqc.get("registered")),
                   "kem_key_len": len(getattr(kem, "public_key", b"") or b"")},
        "features": load_features(),
    }, indent=2))


COMMANDS = {
    "kem": cmd_kem,
    "seal": cmd_seal,
    "anchor-seal": cmd_anchor_seal,
    "anchor": cmd_anchor,
    "receipts": cmd_receipts,
    "anchor-receipts": cmd_anchor_receipts,
    "link-kiosk": cmd_link_kiosk,
    "kiosk-refuse": cmd_kiosk_refuse,
    "window": cmd_window,
    "show": cmd_show,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in {*COMMANDS, "kiosk-checkin", "issue"}:
        print(__doc__)
        return 2
    if argv[0] == "kiosk-checkin":
        cmd_kiosk_checkin(argv[1:])
    elif argv[0] == "issue":
        cmd_issue(argv[1:])
    else:
        COMMANDS[argv[0]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
