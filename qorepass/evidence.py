"""docs/EVIDENCE.md — every claim in the README, generated from the chain.

The document is rebuilt from the deployment record, the journal and live
`eth_call` reads, so a reviewer can open each hash on the explorer and see the
same numbers.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import passes as P
from .config import ROOT

EXPLORER = "https://explore.qore.network"
OUT = ROOT / "docs" / "EVIDENCE.md"
PASS_DIR = ROOT / "demo" / "passes"
JOURNAL = ROOT / "demo" / "journal.jsonl"


def _journal() -> list[dict]:
    if not JOURNAL.exists():
        return []
    return [json.loads(line) for line in JOURNAL.read_text().splitlines() if line.strip()]


def _fmt_ts(value: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(value)) if value else "—"


def write(ctx) -> Path:  # noqa: ANN001 - Context from cli, kept loose to avoid a cycle
    dep = json.loads((ROOT / "keys" / "deployment.json").read_text())
    registry = dep["registry"]
    lines: list[str] = []
    add = lines.append

    add("# Evidence — what `qorechain-diana` actually recorded\n")
    add(
        f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by `python -m qorepass.cli evidence` "
        f"from the chain itself. EVM chain id {dep.get('evm_chain_id')}. Open any hash at "
        f"{EXPLORER}/tx/<hash> with the explorer switched to **Testnet**.\n"
    )
    add("## The contract\n")
    add(f"- registry: `{registry}`")
    add(f"- deploy tx: [`{dep['tx']}`]({EXPLORER}/tx/{dep['tx']}) (block {dep['block']})")
    add(f"- admin: `{dep['admin']}` / `{dep['admin_native']}`")
    add("")

    add("## Accounts\n")
    add("| role | native | EVM | QOR | ML-DSA-87 key on chain |")
    add("| --- | --- | --- | ---: | :---: |")
    for name in ("organizer", "issuer"):
        account = getattr(ctx, name)
        role = {"organizer": "venue / admin", "issuer": "issuer"}[name]
        status = ctx.chain.pqc_status(account.cosmos)
        balance = ctx.chain.uqor(account.cosmos) / 1_000_000
        add(f"| {name} ({role}) | `{account.cosmos}` | `{account.evm}` | {balance:.3f} | {'yes' if status['registered'] else 'no'} |")
    add("")
    add("The demo holders (attendees) have no QoreChain account at all: a pass binds an")
    add("ML-DSA-87 **public key**, so an attendee needs a key, not a wallet, and the")
    add("venue pays the gas for the check-in.\n")

    add("## Registering the issuer's key (the chain's own view)\n")
    try:
        info = ctx.evm.eth_call(registry, P.calldata_issuer_info(ctx.issuer.evm))
        pubkey_hash, name_hash, registered_at, pass_count, nonce, active = __import__("eth_abi").decode(
            ["bytes32", "bytes32", "uint64", "uint32", "uint32", "bool"], bytes.fromhex(info[2:])
        )
        pqc = ctx.chain.pqc_status(ctx.issuer.cosmos)
        add(f"- issuer pubkey hash on chain: `0x{pubkey_hash.hex()}`")
        add(f"- issuer ML-DSA-87 key registered for the account: **{pqc['registered']}**, {len(pqc['pubkey'])} bytes")
        add(f"- registered at {_fmt_ts(registered_at)}, active **{active}**, passes issued **{pass_count}**, approval nonce **{nonce}**")
        add(f"- name hash `0x{name_hash.hex()[:32]}…`")
    except Exception as exc:  # noqa: BLE001
        add(f"- (could not read issuer info: {type(exc).__name__})")
    add("")

    add("## Passes\n")
    add("| pass | holder | event | valid until | state on chain | checked in |")
    add("| --- | --- | --- | --- | --- | --- |")
    for path in sorted(PASS_DIR.glob("*.json")):
        doc = P.PassDocument.load(path)
        try:
            state = __import__("qorepass.cli", fromlist=["onchain_state"]).onchain_state(
                ctx, doc.registry, bytes.fromhex(doc.pass_id[2:])
            )
            state_name = state["state_name"]
            checked = _fmt_ts(state["checked_in_at"])
        except Exception as exc:  # noqa: BLE001
            state_name = f"read error ({type(exc).__name__})"
            checked = "—"
        add(f"| `{path.stem}` | {doc.holder_label} | {doc.event_name} | {_fmt_ts(doc.valid_until)} | **{state_name}** | {checked} |")
    add("")

    add("## Transactions\n")
    add("| # | action | by | result | tx | note |")
    add("| ---: | --- | --- | --- | --- | --- |")
    for i, entry in enumerate(_journal(), start=1):
        ok = entry.get("ok")
        result = "—" if ok is None else ("ok" if ok else "**refused**")
        tx = entry.get("tx") or ""
        link = f"[`{tx[:20]}…`]({EXPLORER}/tx/{tx})" if tx else "—"
        note = str(entry.get("note", "")).replace("|", "/")
        if entry.get("revert"):
            note = f"**{entry['revert']}** — {note}"
        add(f"| {i} | {entry.get('kind')} | {entry.get('actor', '')} | {result} | {link} | {note} |")
    add("")

    add("## Refusals, on chain\n")
    add("A refused call still mines a transaction (`status: 0`) and reverts with the")
    add("contract's own error. These are the ones in the run above:\n")
    for entry in _journal():
        if entry.get("kind") in {"checkin", "issue", "revoke", "forged-issue"} and entry.get("ok") is False:
            add(
                f"- `{entry.get('kind')}` on `{entry.get('pass')}`: "
                f"[`{entry.get('tx')}`]({EXPLORER}/tx/{entry.get('tx')}) — "
                f"**{entry.get('revert') or 'refused'}** ({entry.get('note')})"
            )
    add("")

    add("## How to check it yourself\n")
    add("```bash")
    add(f"# the registry's totals (passState is 0 unknown, 1 valid, 2 checked in, 3 expired, 4 revoked)")
    add(f'curl -s https://api-testnet.qore.host/cosmos/tx/v1beta1/txs/<hash> | jq .tx_response.code, .tx_response.raw_log')
    add("")
    add("# the same reads the web verifier does, straight from the EVM lane")
    add(f'curl -s -X POST https://evm-testnet.qore.host -H "content-type: application/json" \\')
    add(f'  -d \'{{"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{{"to":"{registry}",')
    add(f'  "data":"0x..."}},"latest"]}}\'')
    add("```")
    add("")
    add("The pass documents in `demo/passes/` carry the issuer's 4627-byte ML-DSA-87")
    add("signature; `python -m qorepass.cli verify --pass <name>` recomputes the message")
    add("from the document and verifies that signature offline, with no chain access.")
    add("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    return OUT
