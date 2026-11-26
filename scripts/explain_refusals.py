#!/usr/bin/env python3
"""Backfill the revert reason for every refused transaction in the journal.

A mined-but-reverted EVM transaction stores no reason. This script replays each
one one block earlier and decodes the contract's custom error, then writes the
reason back into `demo/journal.jsonl` so `docs/EVIDENCE.md` can quote it.

    python scripts/explain_refusals.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qorepass.cli import Context  # noqa: E402
from qorepass.config import settings  # noqa: E402
from qorepass.revert import explain  # noqa: E402

JOURNAL = ROOT / "demo" / "journal.jsonl"


def main() -> int:
    ctx = Context(settings())
    entries = [json.loads(line) for line in JOURNAL.read_text().splitlines() if line.strip()]
    changed = 0
    for entry in entries:
        if entry.get("ok") is not False or entry.get("revert"):
            continue
        reason = explain(ctx.evm, entry.get("tx", ""))
        if reason:
            entry["revert"] = reason
            changed += 1
            print(f"{entry['kind']:12s} {entry.get('pass', ''):10s} {reason}")
    JOURNAL.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    print(f"annotated {changed} refusal(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
