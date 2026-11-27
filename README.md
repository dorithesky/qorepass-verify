# QorePass — passes that belong to a post-quantum key, not to a wallet

**Build Before Q-Day · Quantum Pass · QoreChain testnet `qorechain-diana` (EVM chain id 9800)**

[![Built on QoreChain](https://build.qorechain.io/badge/qorepass.svg)](https://build.qorechain.io/p/qorepass)

A pass is a small thing that has to be unforgeable: an event badge, a course
credential, a signed receipt, a door code for one night. Today almost all of
them are a barcode, a PDF, or a row in a database keyed by an account — and
each of those fails the same way twice: a screenshot is as good as the original,
and whoever can sign for the account can mint as many as they like.

QorePass makes the pass belong to an **ML-DSA-87 (FIPS 204) key** instead. The
registry stores `keccak256(holder public key)` at issuance, so checking in needs
the holder's post-quantum signature; the issuer's authorisation is verified by
QoreChain's `pqcVerify` precompile against the key the *chain* holds for the
issuer's account, so an attacker with the issuer's classical (ECDSA) key — the
key a quantum computer would recover — still cannot mint a pass.

> **Name note.** This is `dorithesky/qorepass-verify` — a post-quantum pass
> registry with an on-chain ML-DSA-87 check-in. It is not the other project
> called "QorePass" that appeared in this track on the same day, and not
> "QoreGuard Quantum Pass" (that is a separate treasury agent from the same
> builder). If you are looking for a pass that a *key* owns, you are in the right
> repository: `QorePassRegistry` at `0x312845b8…a88b`.

- **Live verifier:** <https://dorithesky.github.io/qorepass-verify/>
- **QoreX dApp (create-qorechain-dapp + QoreX wallet):** <https://dorithesky.github.io/qorepass-verify/web/dapp/>
- **Contract on testnet:** [`0x312845b8256cafe2ecc8be7addf54f83a836a88b`](https://explore.qore.network/address/0x312845b8256cafe2ecc8be7addf54f83a836a88b) (deploy tx [`0x834f7228…f231`](https://explore.qore.network/tx/0x834f722842fcaa41363de7b233b30c4e772f8ffc4752cf3e2170eb36f466f231), block 10810247)
- **Every hash, generated from the chain:** [`docs/EVIDENCE.md`](docs/EVIDENCE.md)
- **Demo video (≤3 min):** [`demo/qorepass-demo.mp4`](demo/qorepass-demo.mp4)

## The QoreX dApp (`dapp/`)

The verifier page above is a single static file. Next to it, `dapp/` is a real
dApp built the way this track asks for:

```bash
npx create-qorechain-dapp dapp --template viem-wagmi --yes
```

That is the **viem-wagmi** starter from `create-qorechain-dapp@0.14.0` — Vite +
React + wagmi + RainbowKit with `@qorechain/evm`'s chain definitions and
**`@qorechain/qorex-rainbowkit`'s QoreX wallet** as the recommended connector.
On top of the template, QorePass's screens read the registry directly:

- **Look up a pass** by its `bytes32` id: `passInfo` and `passState` are read
  from `QorePassRegistry` and turned into one word — valid, checked in, expired,
  revoked — with the holder-key hash, the event id, the metadata commitment and
  the timestamps. The three demo passes are one tap away.
- **Your account**, once QoreX is connected: balance, the EVM authorisation
  window (native-lane REST), and whether the account is a registered issuer
  (`issuerInfo`: pass count, approval nonce, key hash).
- **Scan receipt**: an EIP-191 signature over "pass X scanned by 0x… at time T",
  a classical signature kept as a venue log — the dApp says plainly that it is
  *not* the post-quantum check-in, which needs the holder's ML-DSA-87 signature
  over `checkInMessage(passId, holderKeyHash)`.

The build is committed under `web/dapp/` so the URL above works without a server
(it needs no proxy: the registry reads go over the EVM JSON-RPC, which serves
CORS). `dapp/` holds the source; `npm install && npm run build` reproduces
`web/dapp/`. Kit: `create-qorechain-dapp`, `@qorechain/evm`,
`@qorechain/qorex-rainbowkit`, wagmi/viem/RainbowKit.

## What the testnet already did

| | |
| --- | --- |
| Registry | `0x312845b8256cafe2ecc8be7addf54f83a836a88b`, admin `qor1m6x0am3atrl4lwyfvgnjn7m3gr20fnvqlktd3n` |
| Issuer | `qor17as3g4qd04j8tveveqafzwxrqlg6gl257cy3xx` — ML-DSA-87 key registered with proof of possession, then registered as an issuer with its own signature |
| Passes | `ada-1` **checked in**, `chen-1` **checked in**, `boram-1` **revoked** (all three documents in `demo/passes/`) |
| Issuer signatures | 4627-byte ML-DSA-87 signatures, each over a 275-byte message bound to this chain, this contract and a per-issuer nonce |
| Hybrid-signed native transactions | key registration ×2, EVM-window opens ×3, funding, and one **anchor** transaction whose memo commits to every pass document |
| Refusals, on chain (mined, `status: 0`) | `AlreadyCheckedIn`, `PassAlreadyRevoked`, `HolderKeyMismatch`, `BadIssuerSignature` — the last one is a *new* pass id forged with the wrong key |
| Tests | 28 Foundry tests, plus an on-chain check that the Python encoder reproduces all four signed messages byte for byte |

The refusals are the interesting half. `0x51509055…c173` is an attacker who
holds the issuer's classical key, submitting a brand-new pass with a signature
made by a different ML-DSA-87 key: it reverts with `BadIssuerSignature()` and
the pass count does not move.

## How a pass works

```
                 issue (one ML-DSA-87 signature by the issuer)
  issuer key ──────────────────────────────────────────────► QorePassRegistry
    │  signs "QOREPASS:v1 | chainid | registry | issuePass | issuer |
    │          passId | holder | eventId | metaHash | holderKeyHash |
    │          validUntil | nonce"
    │                                                          │
    │                            stores: issuer, event, meta hash,
    │                            keccak(holder ML-DSA-87 key), validUntil
    ▼                                                          │
  pass document (JSON, public)  ──► attendee's phone ◄──────────┘
    · passId, event, metadata hash, validUntil
    · holder public key + its hash
    · the issuer's 4627-byte signature

                 check-in (venue scans, venue pays gas)
  holder key ── signs "… | checkIn | passId | holderKeyHash" ──► checkIn()
                                                                 │
                     pqcVerify(holder key, signature, message) ──┤ must be true
                     keccak(holder key) == stored holderKeyHash ─┘ must match
```

Three separate things must be true for a pass to be checked in, and each one
lives somewhere different:

1. **The issuer is who it says.** The registry compares the supplied key with
   `pqcKeyStatus(issuerAccount)` (precompile `0x…0a02`) before verifying any
   signature, so an issuer can only ever sign with the key its own account
   registered.
2. **The pass was authorised once.** Every issue/revoke signature carries a
   monotonic per-issuer nonce, so a captured signature cannot mint a second
   pass or be replayed after the first.
3. **The presenter holds the key.** A pass id on its own is useless: check-in
   needs an ML-DSA-87 signature from the key whose hash was committed at
   issuance (`pqcVerify`, precompile `0x…0a01`).

Every message starts with the domain, `block.chainid` and `address(this)`, so a
signature made for this registry on this chain cannot be replayed on another.

## What QorePass deliberately does not do

- **No wallets for attendees.** A pass is bound to a key, not an account, so the
  venue pays the gas and the attendee never installs anything.
- **No private data on chain.** The chain holds hashes: the event id, a metadata
  hash (tier, seat, name — wherever the organiser keeps them) and the holder's
  key hash. The pass document carries the readable fields.
- **No transfers.** A pass is not an NFT and cannot be sold; moving it would
  mean re-issuing it to another key, which the issuer must sign for.
- **No admin override of a pass.** The admin can suspend an issuer, but cannot
  mint or un-revoke a pass — those need the issuer's own key.

## Quickstart

```bash
git clone https://github.com/dorithesky/qorepass-verify && cd qorepass-verify
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python scripts/bootstrap_keys.py                 # throwaway mnemonics in keys/ (gitignored)
python -m qorepass.cli keygen --holders ada,boram,chen   # attendee ML-DSA-87 keys
python -m qorepass.cli fund --to organizer,issuer --uqor 15000000
python -m qorepass.cli register-pqc organizer
python -m qorepass.cli register-pqc issuer
(cd contracts && forge install foundry-rs/forge-std --no-commit && forge build && forge test)   # 28 tests

# the EVM lane needs a window opened by a hybrid-signed native transaction
python -m qorepass.cli window open --account organizer --txs 1 --blocks 100 --value 1000000
python -m qorepass.cli deploy
REG=$(python -c "import json;print(json.load(open('keys/deployment.json'))['registry'])")
python -m qorepass.cli window open --account organizer --txs 12 --blocks 3000 --target $REG
python -m qorepass.cli window open --account issuer    --txs 12 --blocks 3000 --target $REG

python -m qorepass.cli register-issuer --name "QoreChain Demo Day"
python -m qorepass.cli issue --holder ada --event "QoreChain Demo Day" --valid-days 7 --name ada-1
python -m qorepass.cli checkin --pass ada-1 --holder ada
python -m qorepass.cli verify  --pass ada-1 --onchain
python -m qorepass.cli evidence
```

`keys.env`, `keys/*.key` and the pass holder secrets never leave the machine;
`.gitignore` keeps all of them out of the repository. The test QOR is free and
worth nothing.

## The contract

`contracts/src/QorePassRegistry.sol` (Apache-2.0, Solidity 0.8.24):

| Function | Who | What it checks |
| --- | --- | --- |
| `registerIssuer(pubkey, signature, name)` | any account | its own ML-DSA-87 key is registered on chain, the supplied key is that key, and the signature proves possession |
| `issuePass(passId, holder, eventId, metaHash, holderKeyHash, validUntil, signature)` | a registered issuer | fresh ML-DSA-87 signature over the pass with the issuer's current nonce; pass id unused; validity inside 10 years |
| `checkIn(passId, holderPubkey, holderSignature)` | anyone (venue pays gas) | pass exists, active, unexpired, not yet checked in; holder key hash matches; holder signature verifies |
| `revokePass(passId, reasonHash, signature)` | the issuing account | fresh signature with the current nonce |
| `setIssuerActive(issuer, active)` | admin | issuer exists |
| `passState(passId)` / `passInfo(passId)` / `isValid(passId)` | anyone | 0 unknown · 1 valid · 2 checked in · 3 expired · 4 revoked |

The four `*Message` views return the exact bytes to sign, and
`scripts/verify_encoding.py` compares them with the Python encoder on the live
chain.

## Repository layout

```
contracts/            QorePassRegistry.sol, precompile mocks, 28 Foundry tests
qorepass/             Python package: chain (hybrid txs, windows), evm, passes, cli, evidence
scripts/              key bootstrap, encoder check, refusal explainer, video
web/index.html        the verifier dashboard (no dependencies, reads the chain over JSON-RPC)
demo/passes/*.json    the three issued pass documents, public fields only
demo/journal.jsonl    every action this run took, with tx hashes and revert reasons
docs/EVIDENCE.md      generated from the chain
docs/cover.png        16:9 cover
```

## How it was built

The on-chain side is QoreChain's Python SDK (`qorechain-sdk>=0.15.0`: hybrid
native signatures, EVM windows, PQC key registration) and Foundry for Solidity.
The first pass shipped a single static verifier page because the machine had no
Node toolchain; the second pass installed one (`node` v22) and scaffolded `dapp/`
with the official starter, so the project now has both: the no-build verifier at
the repo root and a `create-qorechain-dapp` viem-wagmi dApp with the QoreX wallet.
The AI workflow behind the build is documented in [`AI_USAGE.md`](AI_USAGE.md),
including what it got wrong.

## Licence

Apache-2.0. Testnet only: every key in this repository's history is a throwaway
test key with no value.
