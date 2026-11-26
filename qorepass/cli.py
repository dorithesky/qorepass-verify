"""QorePass command line.

    python -m qorepass.cli accounts
    python -m qorepass.cli keygen --holders ada,boram,chen
    python -m qorepass.cli fund --uqor 30000000
    python -m qorepass.cli register-pqc organizer
    python -m qorepass.cli window --account organizer --txs 1 --blocks 100
    python -m qorepass.cli deploy
    python -m qorepass.cli register-issuer --name "QoreChain Demo Day"
    python -m qorepass.cli issue --holder ada --event "QoreChain Demo Day" --valid-days 7
    python -m qorepass.cli checkin --pass ada-1 --holder ada
    python -m qorepass.cli revoke --pass boram-1 --reason refunded
    python -m qorepass.cli verify --pass ada-1 --onchain
    python -m qorepass.cli anchor --note "demo day issuance batch 1"
    python -m qorepass.cli state
    python -m qorepass.cli evidence
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from eth_abi import decode as abi_decode
from qorsdk import generate_pqc_keypair, pqc_sign, pqc_verify
from qorsdk.unified import derive_unified_account

from . import passes as P
from .chain import Chain
from .config import ROOT, Settings, format_qor, settings, uqor_to_wei
from .evm import Evm
from .revert import explain

ARTIFACT = ROOT / "contracts" / "out" / "QorePassRegistry.sol" / "QorePassRegistry.json"
DEPLOYMENT = ROOT / "keys" / "deployment.json"
HOLDER_DIR = ROOT / "keys"
PASS_DIR = ROOT / "demo" / "passes"
JOURNAL = ROOT / "demo" / "journal.jsonl"

ZERO = "0x0000000000000000000000000000000000000000"


# ---------------------------------------------------------------------- #
# Plumbing
# ---------------------------------------------------------------------- #
class Context:
    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self.chain = Chain(cfg)
        self.evm = Evm(cfg.evm_rpc, cfg.evm_chain_id)
        self.organizer = derive_unified_account(cfg.organizer_mnemonic) if cfg.organizer_mnemonic else None
        self.issuer = derive_unified_account(cfg.issuer_mnemonic) if cfg.issuer_mnemonic else None
        self.funder = derive_unified_account(cfg.funder_mnemonic) if cfg.funder_mnemonic else None

    # -- deployment ---------------------------------------------------- #
    @property
    def registry(self) -> str:
        if not DEPLOYMENT.exists():
            raise SystemExit("no deployment yet — run `deploy` first")
        return json.loads(DEPLOYMENT.read_text())["registry"]

    # -- pass documents ------------------------------------------------ #
    def pass_path(self, name: str) -> Path:
        return PASS_DIR / f"{name}.json"

    def load_pass(self, name: str) -> P.PassDocument:
        path = self.pass_path(name)
        if not path.exists():
            raise SystemExit(f"no pass document {path}")
        return P.PassDocument.load(path)


def say(label: str, **fields: object) -> None:
    parts = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    print(f"[{label}] {parts}" if parts else f"[{label}]")


def record(entry: dict) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": P.now_ts(), **entry}
    with JOURNAL.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def holder_keys(label: str) -> tuple[bytes, bytes]:
    """(secret, public) ML-DSA-87 key for a demo holder."""
    path = HOLDER_DIR / f"holder-{label}.key"
    if not path.exists():
        raise SystemExit(f"no holder key for {label!r} (run keygen --holders ...)")
    secret = bytes.fromhex(path.read_text().strip())
    pub = (HOLDER_DIR / f"holder-{label}.pub").read_bytes()
    return secret, pub


def account_for(ctx: Context, name: str):
    table = {"organizer": ctx.organizer, "issuer": ctx.issuer, "funder": ctx.funder}
    account = table.get(name)
    if account is None:
        raise SystemExit(f"unknown or unconfigured account {name!r}")
    return account


def window_status(ctx: Context, address: str) -> dict:
    try:
        w = ctx.chain.evm_window(address)
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}
    return {
        "live": w.live,
        "remaining_txs": w.remaining_txs,
        "remaining_blocks": w.remaining_blocks,
        "allowed_targets": list(w.allowed_targets),
    }


# ---------------------------------------------------------------------- #
# Commands
# ---------------------------------------------------------------------- #
def cmd_keygen(ctx: Context, args: argparse.Namespace) -> None:
    from qorsdk import generate_mnemonic

    env_path = HOLDER_DIR / "keys.env"
    existing = env_path.read_text() if env_path.exists() else ""
    needed = {
        "QOREPASS_ORGANIZER_MNEMONIC": ctx.cfg.organizer_mnemonic,
        "QOREPASS_ISSUER_MNEMONIC": ctx.cfg.issuer_mnemonic,
    }
    missing = [f'{key}="{generate_mnemonic()}"' for key, value in needed.items() if not value]
    if missing or not env_path.exists():
        header = "# QorePass throwaway testnet keys — never commit, never use on mainnet"
        body = [line for line in existing.splitlines() if line.strip()] or [header]
        env_path.write_text("\n".join(body + missing) + "\n")
        env_path.chmod(0o600)

    for label in [h.strip() for h in (args.holders or "").split(",") if h.strip()]:
        secret_path = HOLDER_DIR / f"holder-{label}.key"
        pub_path = HOLDER_DIR / f"holder-{label}.pub"
        if secret_path.exists():
            print(f"holder {label}: exists")
            continue
        pair = generate_pqc_keypair()
        secret_path.write_text(pair.secret_key.hex() + "\n")
        secret_path.chmod(0o600)
        pub_path.write_bytes(pair.public_key)
        print(f"holder {label}: new ML-DSA-87 key, pubkey {len(pair.public_key)} bytes, sha256 {P.sha256_hex(pair.public_key)[:16]}…")

    cfg = settings()
    org = derive_unified_account(cfg.organizer_mnemonic) if cfg.organizer_mnemonic else None
    iss = derive_unified_account(cfg.issuer_mnemonic) if cfg.issuer_mnemonic else None
    if org:
        say("organizer", native=org.cosmos, evm=org.evm)
    if iss:
        say("issuer", native=iss.cosmos, evm=iss.evm)


def cmd_accounts(ctx: Context, args: argparse.Namespace) -> None:
    for name in ("funder", "organizer", "issuer"):
        account = account_for(ctx, name)
        print(
            f"{name:10s} {account.cosmos}  {account.evm}  "
            f"{format_qor(ctx.chain.uqor(account.cosmos))}  "
            f"pqc={'yes' if ctx.chain.pqc_status(account.cosmos)['registered'] else 'no'}"
        )
    for label in [h.strip() for h in (args.holders or "").split(",") if h.strip()]:
        _, pub = holder_keys(label)
        print(f"holder {label:8s} ML-DSA-87 key {len(pub)} bytes, hash 0x{P.holder_key_hash(pub).hex()[:16]}…")


def cmd_fund(ctx: Context, args: argparse.Namespace) -> None:
    funder = ctx.funder
    if funder is None:
        raise SystemExit("funder mnemonic missing")
    targets = {"organizer": ctx.organizer, "issuer": ctx.issuer}
    for name in [t.strip() for t in args.to.split(",")]:
        account = targets[name]
        outcome = ctx.chain.send_uqor(funder, account.cosmos, args.uqor, memo=f"qorepass:fund-{name}")
        say("fund", to=name, address=account.cosmos, uqor=args.uqor, tx=outcome.tx_hash, code=outcome.code)
        if not outcome.ok:
            print(outcome.raw_log)
        record({"kind": "fund", "actor": "funder", "to": name, "tx": outcome.tx_hash, "code": outcome.code})
        time.sleep(2)


def cmd_register_pqc(ctx: Context, args: argparse.Namespace) -> None:
    account = account_for(ctx, args.account)
    result = ctx.chain.register_pqc_key(account)
    say("register-pqc", account=args.account, address=account.cosmos, **result)
    record({"kind": "register-pqc", "actor": args.account, "tx": result.get("tx_hash")})


def cmd_window(ctx: Context, args: argparse.Namespace) -> None:
    account = account_for(ctx, args.account)
    if args.action == "status":
        print(json.dumps(window_status(ctx, account.cosmos), indent=2))
        return
    if args.action == "close":
        from qorsdk.messages import msg as compose

        outcome = ctx.chain.send_hybrid(account, [compose.pqc.close_evm_window(sender=account.cosmos)], "qorepass:close-window")
        say("close-window", tx=outcome.tx_hash, code=outcome.code)
        return

    targets = [t for t in (args.target or []) if t]
    outcome = ctx.chain.open_evm_window(
        account,
        blocks=args.blocks,
        max_txs=args.txs,
        max_value_uqor=args.value if args.value else args.txs * 300_000,
        targets=targets,
    )
    say("open-window", account=args.account, tx=outcome.tx_hash, code=outcome.code, targets=targets, txs=args.txs)
    if not outcome.ok:
        print(outcome.raw_log)
        raise SystemExit(1)
    record(
        {
            "kind": "open-window",
            "actor": args.account,
            "tx": outcome.tx_hash,
            "note": f"blocks={args.blocks} txs={args.txs} targets={targets}",
        }
    )
    print(json.dumps(window_status(ctx, account.cosmos), indent=2))


def cmd_deploy(ctx: Context, args: argparse.Namespace) -> None:
    if not ARTIFACT.exists():
        raise SystemExit(f"missing artifact {ARTIFACT} — run `forge build` in contracts/")
    organizer = ctx.organizer
    tx = ctx.evm.deploy(
        organizer.private_key,
        str(ARTIFACT),
        ["address"],
        [organizer.evm],
        gas=args.gas,
        gas_price=ctx.cfg.evm_gas_price_wei,
    )
    receipt = ctx.evm.wait(tx)
    if not receipt.ok or not receipt.contract_address:
        raise SystemExit(f"deploy failed (tx {tx}, status {receipt.status})")
    DEPLOYMENT.write_text(
        json.dumps(
            {
                "registry": receipt.contract_address,
                "tx": tx,
                "block": receipt.block_number,
                "admin": organizer.evm,
                "admin_native": organizer.cosmos,
                "evm_chain_id": ctx.cfg.evm_chain_id,
            },
            indent=2,
        )
        + "\n"
    )
    say(
        "deploy",
        registry=receipt.contract_address,
        tx=tx,
        block=receipt.block_number,
        gas_used=receipt.gas_used,
    )
    record({"kind": "deploy", "actor": "organizer", "tx": tx, "note": receipt.contract_address})


def cmd_register_issuer(ctx: Context, args: argparse.Namespace) -> None:
    issuer = ctx.issuer
    registry = ctx.registry
    pubkey = issuer.pqc.public_key
    name = args.name
    message = P.register_issuer_message(ctx.cfg.evm_chain_id, registry, issuer.evm, P.hash_text(name))
    signature = pqc_sign(issuer.pqc.secret_key, message)
    data = P.calldata_register_issuer(pubkey, signature, name)
    tx = ctx.evm.send(
        issuer.private_key,
        to=registry,
        data=data,
        gas=args.gas,
        gas_price=ctx.cfg.evm_gas_price_wei,
    )
    receipt = ctx.evm.wait(tx)
    say("register-issuer", issuer=issuer.evm, name=name, tx=tx, status="ok" if receipt.ok else "REVERTED")
    record(
        {
            "kind": "register-issuer",
            "actor": "issuer",
            "tx": tx,
            "ok": receipt.ok,
            "note": f"{name} · signed message {len(message)}B, signature {len(signature)}B",
        }
    )
    if not receipt.ok:
        raise SystemExit("registerIssuer reverted")


def cmd_issue(ctx: Context, args: argparse.Namespace) -> None:
    issuer = ctx.issuer
    registry = ctx.registry
    holder = args.holder
    _, holder_pub = holder_keys(holder)
    event_name = args.event
    event_id = P.event_id_for(event_name)
    metadata = json.loads(args.meta) if args.meta else {"holder": holder}
    meta_hash = P.hash_metadata(metadata)
    key_hash = P.holder_key_hash(holder_pub)
    pass_id = P.new_pass_id()
    valid_until = P.now_ts() + int(args.valid_days * 86400)

    nonce = issuer_nonce(ctx, issuer.evm)

    message = P.issue_pass_message(
        ctx.cfg.evm_chain_id, registry, issuer.evm, pass_id, ZERO, event_id, meta_hash, key_hash, valid_until, nonce
    )
    signature = pqc_sign(issuer.pqc.secret_key, message)

    if args.forge_signature:
        # A signature from the organiser's key, presented as the issuer's: the
        # Q-Day case where the attacker has the issuer's classical key but not
        # its ML-DSA-87 secret.
        attacker = ctx.organizer.pqc.secret_key
        signature = pqc_sign(attacker, message)

    data = P.calldata_issue_pass(pass_id, ZERO, event_id, meta_hash, key_hash, valid_until, signature)
    tx = ctx.evm.send(
        issuer.private_key, to=registry, data=data, gas=args.gas, gas_price=ctx.cfg.evm_gas_price_wei
    )
    receipt = ctx.evm.wait(tx)
    revert = "" if receipt.ok else explain(ctx.evm, tx)

    name = args.name or f"{holder}-{int(time.time())}"
    doc = P.PassDocument(
        pass_id="0x" + pass_id.hex(),
        event_id="0x" + event_id.hex(),
        event_name=event_name,
        issuer=issuer.evm,
        holder_label=holder,
        holder_pubkey=P.b64(holder_pub),
        holder_key_hash="0x" + key_hash.hex(),
        holder_address=ZERO,
        meta_hash="0x" + meta_hash.hex(),
        valid_until=valid_until,
        approval_nonce=nonce,
        issued_at=P.now_ts() if receipt.ok else 0,
        issuer_pubkey=P.b64(issuer.pqc.public_key),
        issuer_signature=P.b64(signature),
        registry=registry,
        chain_id=ctx.cfg.evm_chain_id,
        status="issued" if receipt.ok else "refused",
        tx=tx,
        extra={"metadata": metadata},
    )
    doc.save(ctx.pass_path(name))
    say(
        "issue",
        **{
            "pass": name,
            "passId": doc.pass_id[:14] + "…",
            "holder": holder,
            "validUntil": valid_until,
            "nonce": nonce,
            "tx": tx,
            "status": "ok" if receipt.ok else "REFUSED",
        },
    )
    record(
        {
            "kind": "issue",
            "actor": "issuer",
            "pass": name,
            "pass_id": doc.pass_id,
            "holder": holder,
            "tx": tx,
            "ok": receipt.ok,
            "note": f"{event_name} · nonce {nonce} · sig {len(signature)}B" + (" · forged" if args.forge_signature else ""),
            "revert": revert,
        }
    )
    if not receipt.ok:
        print("refused as expected" if args.forge_signature else "issuePass reverted")


def issuer_nonce(ctx: Context, issuer_evm: str) -> int:
    raw = ctx.evm.eth_call(ctx.registry, P.SEL_ISSUER_NONCE + abi_encode_address(issuer_evm))
    return int(raw, 16) if raw and raw != "0x" else 0


def abi_encode_address(address: str) -> bytes:
    from eth_abi import encode as abi_encode

    return abi_encode(["address"], [address])


def cmd_checkin(ctx: Context, args: argparse.Namespace) -> None:
    doc = ctx.load_pass(args.pass_)
    secret, pub = holder_keys(args.holder)
    pass_id = bytes.fromhex(doc.pass_id[2:])
    key_hash = bytes.fromhex(doc.holder_key_hash[2:])

    message = P.check_in_message(doc.chain_id, doc.registry, pass_id, key_hash)
    signature = pqc_sign(secret, message)
    data = P.calldata_check_in(pass_id, pub, signature)
    scanner = account_for(ctx, args.by)
    tx = ctx.evm.send(
        scanner.private_key, to=doc.registry, data=data, gas=args.gas, gas_price=ctx.cfg.evm_gas_price_wei
    )
    receipt = ctx.evm.wait(tx)
    revert = "" if receipt.ok else explain(ctx.evm, tx)
    state = onchain_state(ctx, doc.registry, pass_id)
    say(
        "checkin",
        **{
            "pass": args.pass_,
            "holder": args.holder,
            "by": args.by,
            "tx": tx,
            "status": "ok" if receipt.ok else "REFUSED",
            "onchain": state["state_name"],
            "revert": revert or None,
        },
    )
    record(
        {
            "kind": "checkin",
            "actor": args.by,
            "pass": args.pass_,
            "holder": args.holder,
            "tx": tx,
            "ok": receipt.ok,
            "note": f"holder signature over {len(message)}B message, sig {len(signature)}B, state {state['state_name']}",
            "revert": revert,
        }
    )
    if not receipt.ok and not args.allow_refusal:
        print("checkIn reverted")


def cmd_revoke(ctx: Context, args: argparse.Namespace) -> None:
    doc = ctx.load_pass(args.pass_)
    issuer = ctx.issuer
    pass_id = bytes.fromhex(doc.pass_id[2:])
    reason_hash = P.hash_text(args.reason)
    nonce = issuer_nonce(ctx, issuer.evm)
    message = P.revoke_pass_message(doc.chain_id, doc.registry, issuer.evm, pass_id, reason_hash, nonce)
    signature = pqc_sign(issuer.pqc.secret_key, message)
    data = P.calldata_revoke_pass(pass_id, reason_hash, signature)
    tx = ctx.evm.send(issuer.private_key, to=doc.registry, data=data, gas=args.gas, gas_price=ctx.cfg.evm_gas_price_wei)
    receipt = ctx.evm.wait(tx)
    revert = "" if receipt.ok else explain(ctx.evm, tx)
    state = onchain_state(ctx, doc.registry, pass_id)
    doc.status = "revoked" if receipt.ok else doc.status
    doc.save(ctx.pass_path(args.pass_))
    say(
        "revoke",
        **{"pass": args.pass_, "reason": args.reason, "nonce": nonce, "tx": tx, "status": "ok" if receipt.ok else "REFUSED", "onchain": state["state_name"]},
    )
    record(
        {
            "kind": "revoke",
            "actor": "issuer",
            "pass": args.pass_,
            "tx": tx,
            "ok": receipt.ok,
            "note": f"reason '{args.reason}' · nonce {nonce} · state {state['state_name']}",
            "revert": revert,
        }
    )


def onchain_state(ctx: Context, registry: str, pass_id: bytes) -> dict:
    raw_state = ctx.evm.eth_call(registry, P.calldata_pass_state(pass_id))
    state = abi_decode(["uint8"], bytes.fromhex(raw_state[2:]))[0]
    raw_info = ctx.evm.eth_call(registry, P.calldata_pass_info(pass_id))
    (
        issuer,
        holder,
        event_id,
        meta_hash,
        key_hash,
        valid_until,
        issued_at,
        checked_in_at,
        status,
    ) = abi_decode(
        ["address", "address", "bytes32", "bytes32", "bytes32", "uint64", "uint64", "uint64", "uint8"],
        bytes.fromhex(raw_info[2:]),
    )
    return {
        "state": state,
        "state_name": P.STATE_NAMES.get(state, "?"),
        "issuer": issuer,
        "holder": holder,
        "event_id": "0x" + event_id.hex(),
        "meta_hash": "0x" + meta_hash.hex(),
        "holder_key_hash": "0x" + key_hash.hex(),
        "valid_until": valid_until,
        "issued_at": issued_at,
        "checked_in_at": checked_in_at,
        "status": status,
    }


def cmd_verify(ctx: Context, args: argparse.Namespace) -> None:
    doc = ctx.load_pass(args.pass_)
    pass_id = bytes.fromhex(doc.pass_id[2:])
    issuer_pub = P.from_b64(doc.issuer_pubkey)
    signature = P.from_b64(doc.issuer_signature)
    offline = pqc_verify(issuer_pub, doc.issue_message(), signature)
    valid_until = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(doc.valid_until))
    print(f"pass      {doc.pass_id}")
    print(f"event     {doc.event_name}")
    print(f"holder    {doc.holder_label} · key hash {doc.holder_key_hash[:18]}…")
    print(f"validUntil {valid_until}")
    print(f"issuer signature verifies offline: {offline}")
    if args.onchain:
        state = onchain_state(ctx, doc.registry, pass_id)
        print(f"on chain  state={state['state_name']} checkedInAt={state['checked_in_at']} issuer={state['issuer']}")
        print(f"key hash matches on chain: {state['holder_key_hash'] == doc.holder_key_hash}")


def cmd_anchor(ctx: Context, args: argparse.Namespace) -> None:
    """One hybrid-signed native transaction that commits to the demo state.

    The memo carries a digest of every pass document, so the whole batch is
    timestamped by a transaction whose signature is ML-DSA-87 + secp256k1.
    """
    import hashlib

    digests = []
    for path in sorted(PASS_DIR.glob("*.json")):
        digests.append(hashlib.sha256(path.read_bytes()).hexdigest())
    root = hashlib.sha256("".join(digests).encode()).hexdigest()
    memo = f"qorepass:v1:{root}"
    organizer = ctx.organizer
    outcome = ctx.chain.send_uqor(organizer, organizer.cosmos, 1, memo=memo)
    say("anchor", tx=outcome.tx_hash, code=outcome.code, memo=memo, docs=len(digests))
    record({"kind": "anchor", "actor": "organizer", "tx": outcome.tx_hash, "ok": outcome.ok, "note": memo})


def cmd_attack(ctx: Context, args: argparse.Namespace) -> None:
    """Try to mint a *new* pass with a signature from the wrong ML-DSA-87 key.

    The attacker submits from the issuer's own account, i.e. it holds the issuer's
    classical (ECDSA) key — the key a quantum computer would recover. What it
    does not hold is the issuer's ML-DSA-87 secret, so the contract must refuse.
    """
    doc = ctx.load_pass(args.pass_)
    issuer = ctx.issuer
    pass_id = P.new_pass_id()  # fresh id: the duplicate check must not be what refuses this
    nonce = issuer_nonce(ctx, issuer.evm)
    message = P.issue_pass_message(
        doc.chain_id,
        doc.registry,
        issuer.evm,
        pass_id,
        doc.holder_address,
        bytes.fromhex(doc.event_id[2:]),
        bytes.fromhex(doc.meta_hash[2:]),
        bytes.fromhex(doc.holder_key_hash[2:]),
        doc.valid_until,
        nonce,
    )
    forged = pqc_sign(ctx.organizer.pqc.secret_key, message)
    data = P.calldata_issue_pass(
        pass_id, doc.holder_address, bytes.fromhex(doc.event_id[2:]), bytes.fromhex(doc.meta_hash[2:]),
        bytes.fromhex(doc.holder_key_hash[2:]), doc.valid_until, forged,
    )
    tx = ctx.evm.send(issuer.private_key, to=doc.registry, data=data, gas=900_000, gas_price=ctx.cfg.evm_gas_price_wei)
    receipt = ctx.evm.wait(tx)
    revert = "" if receipt.ok else explain(ctx.evm, tx)
    say(
        "forged-issue",
        **{"passId": "0x" + pass_id.hex()[:14] + "…", "tx": tx, "status": "ACCEPTED" if receipt.ok else "REFUSED", "revert": revert or None},
    )
    record(
        {
            "kind": "forged-issue",
            "actor": "attacker holding the issuer's classical key",
            "pass": "0x" + pass_id.hex()[:14] + "…",
            "tx": tx,
            "ok": receipt.ok,
            "note": "new pass id, signature made with a key that is not the issuer's ML-DSA-87 key",
            "revert": revert,
        }
    )
    if receipt.ok:
        raise SystemExit("the forged pass was accepted — this is a bug")


def cmd_state(ctx: Context, args: argparse.Namespace) -> None:
    registry = ctx.registry
    totals = {}
    for name, selector in (
        ("issued", P.SEL_TOTAL_ISSUED),
        ("checked_in", P.SEL_TOTAL_CHECKED_IN),
        ("revoked", P.SEL_TOTAL_REVOKED),
    ):
        raw = ctx.evm.eth_call(registry, selector)
        totals[name] = int(raw, 16) if raw and raw != "0x" else 0
    print(f"registry {registry}")
    print(json.dumps(totals))
    for name in ("organizer", "issuer"):
        account = account_for(ctx, name)
        print(f"{name}: {format_qor(ctx.chain.uqor(account.cosmos))} window={json.dumps(window_status(ctx, account.cosmos))}")
    for path in sorted(PASS_DIR.glob("*.json")):
        doc = P.PassDocument.load(path)
        state = onchain_state(ctx, doc.registry, bytes.fromhex(doc.pass_id[2:]))
        print(f"  {path.stem:12s} {doc.holder_label:6s} {state['state_name']:10s} {doc.pass_id[:14]}…")


def cmd_evidence(ctx: Context, args: argparse.Namespace) -> None:
    from . import evidence

    path = evidence.write(ctx)
    print(f"wrote {path}")


# ---------------------------------------------------------------------- #
# Parser
# ---------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qorepass", description="QorePass on QoreChain testnet")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("keygen", help="create throwaway keys")
    p.add_argument("--holders", default="ada,boram,chen")
    p.set_defaults(func=cmd_keygen)

    p = sub.add_parser("accounts", help="show accounts and balances")
    p.add_argument("--holders", default="ada,boram,chen")
    p.set_defaults(func=cmd_accounts)

    p = sub.add_parser("fund", help="send test QOR from the funder account")
    p.add_argument("--to", default="organizer,issuer")
    p.add_argument("--uqor", type=int, default=15_000_000)
    p.set_defaults(func=cmd_fund)

    p = sub.add_parser("register-pqc", help="register the account's ML-DSA-87 key")
    p.add_argument("account", choices=["organizer", "issuer"])
    p.set_defaults(func=cmd_register_pqc)

    p = sub.add_parser("window", help="EVM window")
    p.add_argument("action", choices=["open", "close", "status"])
    p.add_argument("--account", default="organizer")
    p.add_argument("--blocks", type=int, default=2000)
    p.add_argument("--txs", type=int, default=10)
    p.add_argument("--value", type=int, default=0, help="max_value in uqor (default: txs x 300000)")
    p.add_argument("--target", action="append")
    p.set_defaults(func=cmd_window)

    p = sub.add_parser("deploy", help="deploy QorePassRegistry")
    p.add_argument("--gas", type=int, default=4_000_000)
    p.set_defaults(func=cmd_deploy)

    p = sub.add_parser("register-issuer", help="register the issuer's key on chain")
    p.add_argument("--name", default="QoreChain Demo Day")
    p.add_argument("--gas", type=int, default=1_200_000)
    p.set_defaults(func=cmd_register_issuer)

    p = sub.add_parser("issue", help="issue a pass")
    p.add_argument("--holder", required=True)
    p.add_argument("--event", default="QoreChain Demo Day")
    p.add_argument("--meta", default="")
    p.add_argument("--valid-days", type=float, default=7)
    p.add_argument("--name", default="")
    p.add_argument("--gas", type=int, default=900_000)
    p.add_argument("--forge-signature", action="store_true")
    p.set_defaults(func=cmd_issue)

    p = sub.add_parser("checkin", help="check a pass in with the holder's key")
    p.add_argument("--pass", dest="pass_", required=True)
    p.add_argument("--holder", required=True)
    p.add_argument("--by", default="organizer")
    p.add_argument("--gas", type=int, default=900_000)
    p.add_argument("--allow-refusal", action="store_true")
    p.set_defaults(func=cmd_checkin)

    p = sub.add_parser("revoke", help="revoke a pass")
    p.add_argument("--pass", dest="pass_", required=True)
    p.add_argument("--reason", default="refunded")
    p.add_argument("--gas", type=int, default=900_000)
    p.set_defaults(func=cmd_revoke)

    p = sub.add_parser("verify", help="verify a pass document")
    p.add_argument("--pass", dest="pass_", required=True)
    p.add_argument("--onchain", action="store_true")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("anchor", help="hybrid-signed anchor over the pass documents")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_anchor)

    p = sub.add_parser("attack", help="try to mint with the wrong PQ key")
    p.add_argument("--pass", dest="pass_", required=True)
    p.set_defaults(func=cmd_attack)

    p = sub.add_parser("state", help="registry + account state")
    p.set_defaults(func=cmd_state)

    p = sub.add_parser("evidence", help="write docs/EVIDENCE.md from the chain")
    p.set_defaults(func=cmd_evidence)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = settings()
    ctx = Context(cfg)
    try:
        args.func(ctx, args)
    except SystemExit as exc:
        if exc.code not in (0, None):
            print(exc, file=sys.stderr)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
