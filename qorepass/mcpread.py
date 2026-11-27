"""The read layer, over the QoreChain MCP server (`qorechain-mcp`).

The kit ships a Model Context Protocol server that answers questions about a
QoreChain network — an account's balances, whether a key is registered, a
transaction's hybrid-signature status, and any EVM view function
(`read_contract`). QorePass's read-only surfaces go through that server instead
of hand-rolled REST calls, so the same answers are available to any MCP client —
an editor, another agent, or a judge's own tooling — with no credentials.

Nothing here can write: every tool in `qorechain-mcp` is read-only by design.
The registry's own rules are what stop a pass from being forged; this module
cannot even see a key.

    python -m qorepass.mcpread state      # registry totals via MCP tools
    python -m qorepass.mcpread pass 0x…   # one pass, via read_contract
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = [sys.executable, "-m", "qorechain_mcp"]


def _server_params() -> StdioServerParameters:
    env = dict(os.environ)
    env.setdefault("QORECHAIN_MCP_NETWORK", "testnet")
    return StdioServerParameters(command=SERVER[0], args=SERVER[1:], env=env)


async def _with_session(fn):  # noqa: ANN001
    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(_server_params()))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return await fn(session)


async def _call(session: ClientSession, name: str, args: dict[str, Any]) -> dict[str, Any]:
    result = await session.call_tool(name, args)
    if getattr(result, "isError", False):
        raise RuntimeError(f"{name} failed: {result.content}")
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
    return {}


def call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call one QoreChain MCP tool and return its JSON answer."""

    async def run():
        return await _with_session(lambda s: _call(s, name, args))

    return asyncio.run(run())


def list_tools() -> list[str]:
    async def run():
        return await _with_session(_tools)

    return asyncio.run(run())


async def _tools(session: ClientSession) -> list[str]:
    listed = await session.list_tools()
    return [t.name for t in listed.tools]


def _hex(result: dict[str, Any]) -> str:
    raw = result.get("result") or result.get("return") or ""
    if isinstance(raw, dict):
        raw = raw.get("data", "")
    raw = str(raw)
    return raw[2:] if raw.startswith("0x") else raw


def read_uint(contract: str, function: str, args: list[str] | None = None) -> int:
    """One uint256 view through the MCP server."""
    request: dict[str, Any] = {"to": contract, "function": function, "network": "testnet"}
    if args:
        request["args"] = args
    raw = _hex(call("read_contract", request))
    return int(raw, 16) if raw else 0


def read_raw(contract: str, function: str, args: list[str] | None = None) -> str:
    request: dict[str, Any] = {"to": contract, "function": function, "network": "testnet"}
    if args:
        request["args"] = args
    return _hex(call("read_contract", request))


def registry_state(contract: str) -> dict[str, Any]:
    """The registry as the chain sees it, read the MCP way."""
    return {
        "issued": read_uint(contract, "totalIssued()"),
        "checkedIn": read_uint(contract, "totalCheckedIn()"),
        "revoked": read_uint(contract, "totalRevoked()"),
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"tools", "list"}:
        print(json.dumps({"tools": list_tools()}, indent=2))
        return 0
    if argv[0] == "state":
        from .cli import Context
        from .config import settings

        ctx = Context(settings())
        print(json.dumps({"registry": ctx.registry, **registry_state(ctx.registry)}, indent=2))
        return 0
    if argv[0] == "pass" and len(argv) > 1:
        from .cli import Context
        from .config import settings

        ctx = Context(settings())
        print(json.dumps({"passState": read_uint(ctx.registry, "passState(bytes32)", [argv[1]])}, indent=2))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
