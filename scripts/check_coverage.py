#!/usr/bin/env python3
"""Fail the build if `forge coverage` is not 100% on the registry.

    forge coverage --report summary --no-match-coverage "test|mocks" | tee coverage.txt
    python scripts/check_coverage.py coverage.txt

Used by `.github/workflows/daily-verify.yml`. The gate is deliberately on the
four numbers the table prints (lines, statements, branches, functions), because
a line can be executed without its branch being taken — the branch column is the
one that catches a guard whose refusal path is never tested.
"""

from __future__ import annotations

import sys
from pathlib import Path

WANT = ["100.00%"] * 4


def main(argv: list[str]) -> int:
    path = Path(argv[0] if argv else "coverage.txt")
    if not path.exists():
        print(f"no coverage report at {path}", file=sys.stderr)
        return 2
    row = next((line for line in path.read_text().splitlines() if "QorePassRegistry.sol" in line), "")
    if not row:
        print("the coverage table has no QorePassRegistry.sol row", file=sys.stderr)
        return 2
    cells = [cell.strip() for cell in row.strip().strip("|").split("|")][1:]
    numbers = [cell.split()[0] for cell in cells]
    print("coverage:", " ".join(f"{name}={value}" for name, value in zip(("lines", "statements", "branches", "functions"), numbers)))
    if numbers[:4] != WANT:
        print(f"coverage fell below 100%: {numbers[:4]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
