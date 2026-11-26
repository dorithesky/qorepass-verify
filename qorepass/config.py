"""Configuration for QorePass on QoreChain testnet `qorechain-diana`.

Every key this project uses is a throwaway testnet key created by
`scripts/bootstrap_keys.py` and stored in `keys/`, which is gitignored. Nothing
here is worth anything, and nothing here should ever touch mainnet.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path: Path) -> None:
    """Read KEY=value lines into os.environ without overriding what is set."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(ROOT / "keys" / "keys.env")
load_env_file(ROOT / ".env")

#: 1 uqor = 10^12 wei on the EVM lane.
WEI_PER_UQOR = 10**12


@dataclass(frozen=True)
class Settings:
    chain_id: str
    rest: str
    rpc: str
    evm_rpc: str
    evm_chain_id: int
    organizer_mnemonic: str
    issuer_mnemonic: str
    relayer_mnemonic: str
    funder_mnemonic: str

    # Native lane fees. The network floor is 0.1 uqor/gas; 0.15 keeps a hybrid
    # transaction ahead of the floor.
    gas: int = 1_500_000
    fee_uqor: int = 225_000

    # EVM lane.
    evm_gas_price_wei: int = 120_000_000_000  # 120 gwei (base fee is 100 gwei)
    evm_gas_deploy: int = 4_000_000
    evm_gas_call: int = 900_000

    @property
    def keys_dir(self) -> Path:
        return ROOT / "keys"


def settings() -> Settings:
    def get(name: str, default: str = "") -> str:
        return os.environ.get(name, default)

    return Settings(
        chain_id=get("QORE_CHAIN_ID", "qorechain-diana"),
        rest=get("QORE_REST", "https://api-testnet.qore.host"),
        rpc=get("QORE_RPC", "https://rpc-testnet.qore.host"),
        evm_rpc=get("QORE_EVM_RPC", "https://evm-testnet.qore.host"),
        evm_chain_id=int(get("QORE_EVM_CHAIN_ID", "9800")),
        organizer_mnemonic=get("QOREPASS_ORGANIZER_MNEMONIC"),
        issuer_mnemonic=get("QOREPASS_ISSUER_MNEMONIC"),
        relayer_mnemonic=get("QOREPASS_RELAYER_MNEMONIC"),
        funder_mnemonic=get("QOREPASS_FUNDER_MNEMONIC"),
    )


def uqor_to_wei(amount_uqor: int) -> int:
    return amount_uqor * WEI_PER_UQOR


def format_qor(amount_uqor: int | str) -> str:
    return f"{Decimal(int(amount_uqor)) / Decimal(1_000_000):.6f} QOR"
