"""QoreSign: the venue's check-in receipt, signed as a Sign In With QoreChain message.

A check-in is two separate statements, and QorePass keeps them separate on
purpose:

* **The pass is real** — `QorePassRegistry` verified the holder's ML-DSA-87
  signature on chain. That is the gate.
* **This venue admitted this holder at this time** — a statement by the venue's
  account, which is what an attendee, an auditor or a dispute needs afterwards.

The second statement is a **Sign In With QoreChain** message
(`qorechain-qoresign`), signed by the venue's hybrid key pair — secp256k1 for
the classical layer, ML-DSA-87 for the post-quantum one. It is verified against
the ML-DSA-87 key registered for the venue account **on chain**, not against a
key the receipt carries, so a receipt cannot be forged by anyone who merely has
the venue's classical key (the key a quantum computer would recover).

Each receipt binds the pass id, the holder's key hash, the event, the check-in
time and the registry address, and it carries a nonce and an expiry, so a
receipt cannot be re-pointed at another pass or replayed as a fresh admission.
"""

from __future__ import annotations

import datetime as _dt
import secrets
from dataclasses import dataclass

import qoresign

#: The authority that issues admission receipts. Fixed, because it is part of
#: what the venue signs and what the verifier checks.
DOMAIN = "qorepass.venue"
URI = "qorechain:qorepass.venue"
#: How long a receipt's signature stays usable. A receipt is a record, so this
#: is generous; verification judges it at its issue time.
DEFAULT_TTL_SECONDS = 24 * 60 * 60


def statement(
    *,
    pass_name: str,
    pass_id: str,
    holder_label: str,
    holder_key_hash: str,
    event_name: str,
    registry: str,
    checked_in_at: int,
) -> str:
    """The one line the venue signs, and the one line a reader checks."""
    when = _dt.datetime.fromtimestamp(checked_in_at, _dt.timezone.utc).replace(microsecond=0)
    return (
        f"Admit {pass_name} ({pass_id}) to {event_name}: holder {holder_label}, "
        f"key hash {holder_key_hash}, at {when.isoformat().replace('+00:00', 'Z')}, "
        f"registry {registry}"
    )


def _iso(when: _dt.datetime) -> str:
    return when.replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Receipt:
    """What the venue's wallet renders and signs, and what a verifier checks."""

    message: str
    nonce: str
    pass_name: str
    pass_id: str
    holder_label: str
    holder_key_hash: str
    event_name: str
    registry: str
    checked_in_at: int

    def as_dict(self) -> dict:
        return {
            "message": self.message,
            "nonce": self.nonce,
            "pass": self.pass_name,
            "pass_id": self.pass_id,
            "holder": self.holder_label,
            "holder_key_hash": self.holder_key_hash,
            "event": self.event_name,
            "registry": self.registry,
            "checked_in_at": self.checked_in_at,
        }


def build_receipt(
    *,
    account: str,
    chain_id: str,
    pass_name: str,
    pass_id: str,
    holder_label: str,
    holder_key_hash: str,
    event_name: str,
    registry: str,
    checked_in_at: int,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: _dt.datetime | None = None,
) -> Receipt:
    """Render the SIWQ message the venue signs for one admitted pass."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    nonce = "rcpt" + secrets.token_hex(6)
    fields = qoresign.SiwqFields(
        domain=DOMAIN,
        address=account,
        uri=URI,
        chain_id=chain_id,
        nonce=nonce,
        issued_at=_iso(now),
        statement=statement(
            pass_name=pass_name,
            pass_id=pass_id,
            holder_label=holder_label,
            holder_key_hash=holder_key_hash,
            event_name=event_name,
            registry=registry,
            checked_in_at=checked_in_at,
        ),
        expiration_time=_iso(now + _dt.timedelta(seconds=ttl_seconds)),
    )
    return Receipt(
        message=qoresign.create_siwq_message(fields),
        nonce=nonce,
        pass_name=pass_name,
        pass_id=pass_id,
        holder_label=holder_label,
        holder_key_hash=holder_key_hash,
        event_name=event_name,
        registry=registry,
        checked_in_at=checked_in_at,
    )


def sign(receipt: Receipt, mnemonic: str, account: str) -> str:
    """Sign on the venue's side: hybrid secp256k1 + ML-DSA-87, as a wallet does."""
    classical = qoresign.derive_classical_key(mnemonic, qoresign.ClassicalKeyType.ETH_SECP256K1)
    pq = qoresign.derive_canonical_pq_key(mnemonic, account)
    signature = qoresign.sign_siwq(receipt.message, classical, pq_key=pq)
    return qoresign.siwq_signature_to_json(signature)


def verify(
    receipt: Receipt,
    signature_json: str,
    *,
    chain_pq_public_key: bytes,
    chain_id: str,
    at_ms: int | None = None,
) -> dict:
    """Verify a receipt against the venue's on-chain ML-DSA-87 key.

    `at_ms` should be the receipt's own issue time: the signature is judged as
    of when it was made, and its expiry still applies. Without it the check runs
    against now, which is what a live gate would do.
    """
    signature = qoresign.siwq_signature_from_json(signature_json)
    fields = qoresign.parse_siwq_message(receipt.message)
    if fields.domain != DOMAIN:
        raise ValueError(f"receipt domain is {fields.domain!r}, not {DOMAIN!r}")
    if receipt.nonce not in receipt.message:
        raise ValueError("the receipt nonce is not in the signed message")
    for wanted in (
        receipt.pass_id,
        receipt.holder_key_hash,
        receipt.registry,
    ):
        if wanted not in receipt.message:
            raise ValueError(f"{wanted} is not in the signed message")
    kwargs: dict = {
        "domain": DOMAIN,
        "nonce": receipt.nonce,
        "pq_public_key": chain_pq_public_key,
        "chain_id": chain_id,
        "require_pq": True,
    }
    if at_ms is not None:
        kwargs["now_ms"] = at_ms
    return qoresign.verify_siwq(receipt.message, signature, **kwargs)


def issued_ms(message: str) -> int:
    """The `Issued At` instant of a SIWQ message, in milliseconds."""
    for line in message.splitlines():
        if line.startswith("Issued At:"):
            stamp = line.split(":", 1)[1].strip().rstrip("Z")
            return int(_dt.datetime.fromisoformat(stamp).replace(tzinfo=_dt.timezone.utc).timestamp() * 1000)
    raise ValueError("the SIWQ message has no Issued At line")


def memo(receipts: list[Receipt]) -> str:
    """One commitment for a batch of receipts, short enough for a native memo."""
    import hashlib
    import json as _json

    digest = hashlib.sha256(
        "|".join(sorted(_json.dumps(r.as_dict(), sort_keys=True, separators=(",", ":")) for r in receipts)).encode()
    ).hexdigest()
    return f"qorepass:receipts:v1:{digest[:40]}"
