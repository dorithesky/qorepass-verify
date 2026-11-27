"""QoreSeal: the issuance archive only the issuer can open.

A pass registry's archive is the sensitive half of the demo: it holds every
issued pass document, the holder labels behind each key hash, the metadata
commitments and the issuer's signature for each pass. Publishing that as a
plain JSON directory next to the chain records would hand anyone the mapping
from a key hash to a person.

QorePass therefore seals the archive before it anchors it:

1. the issuer builds one archive file (every pass document, byte for byte),
2. the archive is sealed to the **issuer's ML-KEM-1024 key** with
   `qorechain-qoreseal` (hybrid X25519 + ML-KEM-1024, the envelope bound to the
   chain, the purpose and an AAD of the batch id), and
3. only a 32-byte digest of the sealed envelope goes on chain, in the memo of a
   hybrid-signed transaction.

The issuer re-derives the same sealing key from the same mnemonic, so the
archive opens offline, years later, with no service and no shared secret.
Anyone without the ML-KEM secret key — a quantum computer included — gets an
authentication failure, not a padded plaintext.

    python -m qorepass.sealing show      # what is sealed, and where
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import qoreseal

#: Bound into every envelope, so a sealed archive cannot be replayed as another
#: kind of document, on another chain, or against another batch.
PURPOSE = "qorepass/issuance-archive/v1"


@dataclass(frozen=True)
class Sealed:
    """One sealed archive: where it is, and what the chain commits to."""

    batch_id: str
    path: Path
    envelope_sha256: str
    envelope_len: int
    plaintext_sha256: str
    entries: int

    @property
    def memo(self) -> str:
        """The invariant part of the on-chain memo: a commitment to this exact
        envelope. 40 hex characters keep the memo short and the commitment
        unforgeable."""
        return f"qorepass:seal:v1:{self.envelope_sha256[:40]}"

    def as_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "envelope": str(self.path),
            "envelope_sha256": self.envelope_sha256,
            "envelope_len": self.envelope_len,
            "plaintext_sha256": self.plaintext_sha256,
            "entries": self.entries,
            "memo_commitment": self.memo,
        }


def seal_keys(mnemonic: str) -> "qoreseal.SealKeyPair":
    """The issuer's QoreSeal key pair, derived from the account mnemonic."""
    return qoreseal.seal_keys_from_seed(qoreseal.seal_seed_from_mnemonic(mnemonic))


def _aad(batch_id: str) -> bytes:
    return f"qorepass:archive:{batch_id}".encode()


def build_archive(pass_dir: Path) -> tuple[bytes, int]:
    """The archive bytes: a manifest plus every pass document, exactly as
    stored. Deterministic (sorted paths, fixed separators), so the digest can be
    reproduced by anyone holding the same files."""
    files = sorted(pass_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no pass documents under {pass_dir}")
    header = {
        "format": "qorepass/issuance-archive/v1",
        "documents": [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],
    }
    body = json.dumps(header, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    for path in files:
        body += path.read_bytes()
    return body, len(files)


def seal_archive(
    keys: "qoreseal.SealKeyPair",
    batch_id: str,
    plaintext: bytes,
    entries: int,
    out_dir: Path,
    *,
    chain_id: str = "qorechain-diana",
) -> Sealed:
    """Encrypt one archive to the issuer's key and write the envelope."""
    envelope = qoreseal.seal_envelope(
        chain_id=chain_id,
        purpose=PURPOSE,
        recipients=[
            qoreseal.SealRecipient(
                mlkem_public_key=keys.mlkem_public_key,
                x25519_public_key=keys.x25519_public_key,
            )
        ],
        plaintext=plaintext,
        aad=_aad(batch_id),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{batch_id}.sealed"
    path.write_bytes(envelope)
    return Sealed(
        batch_id=batch_id,
        path=path,
        envelope_sha256=hashlib.sha256(envelope).hexdigest(),
        envelope_len=len(envelope),
        plaintext_sha256=hashlib.sha256(plaintext).hexdigest(),
        entries=entries,
    )


def open_archive(
    keys: "qoreseal.SealKeyPair",
    sealed: Sealed | Path,
    batch_id: str,
    *,
    chain_id: str = "qorechain-diana",
) -> bytes:
    """Decrypt a sealed archive with the issuer's keys.

    Raises `qoreseal.QoreSealError` if the envelope was sealed to another
    recipient, for another chain, purpose or batch id, or if it was modified.
    """
    path = sealed.path if isinstance(sealed, Sealed) else sealed
    return qoreseal.open_envelope(
        chain_id=chain_id,
        purpose=PURPOSE,
        envelope=path.read_bytes(),
        keys=keys,
        aad=_aad(batch_id),
    )


def without_secrets(document: dict) -> dict:
    """What the demo publishes: the documents minus nothing secret (pass
    documents carry no secret), kept here so a caller does not have to guess."""
    return document


INDEX = "index.json"


def write_index(out_dir: Path, records: list[Sealed]) -> Path:
    path = out_dir / INDEX
    path.write_text(json.dumps([r.as_dict() for r in records], indent=2) + "\n")
    return path


def read_index(out_dir: Path) -> list[dict]:
    path = out_dir / INDEX
    return json.loads(path.read_text()) if path.exists() else []
