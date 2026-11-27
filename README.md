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
- **Re-check it yourself, with no key:** `python verify.py` — 27 read-only checks, ~30 seconds
- **Every hash, generated from the chain:** [`docs/EVIDENCE.md`](docs/EVIDENCE.md)
- **Demo video (2:32):** [`demo/qorepass-demo.mp4`](demo/qorepass-demo.mp4)

## Re-check it in one command (no key, no wallet, nothing signed)

```bash
pip install -r requirements.txt
python verify.py            # or: python verify.py --json
```

`verify.py` reads only public endpoints and the files in this repository. It
checks, and prints what it compared:

| # | What it establishes |
| ---: | --- |
| 1–4 | the REST and EVM endpoints are `qorechain-diana` / 9800, the deployed **bytecode is the audited artifact** (only the two `admin` immutables differ), the deploy transaction created this address |
| 5–8 | the registry's totals are the journal's actions; **every pass state is what the journal recorded** (`ada-1`, `chen-1`, `dara-1` checked in, `boram-1` revoked, `eun-1` valid); the issuer is the account whose ML-DSA-87 key the chain holds, with `passCount` and `approvalNonce` matching its authorisations; the issuer's **ML-KEM-1024 key** is on chain |
| 9–11 | all 15 EVM and all 19 native (hybrid-signed) journaled transactions are on chain with their recorded outcome; anchors carry their commitment; the 6 refusals are transactions |
| 12–15 | the gates still refuse, **reproduced now by `eth_call`**: a second check-in (`AlreadyCheckedIn`), a revoked pass (`PassAlreadyRevoked`), another holder's key (`HolderKeyMismatch`), a forged ML-DSA-87 issuer signature (`BadIssuerSignature`) |
| 16–17 | every pass document's 4627-byte issuer signature verifies **offline**, and the message it signed is byte-for-byte the contract's own `issuePassMessage` view |
| 18–19 | the sealed issuance archive still hashes to the digest its anchor transaction carries (QoreSeal) |
| 20–22 | each check-in receipt verifies against the venue's on-chain key at its issue time, while an edited time, a re-pointed pass id and the same receipt 25 h later are refused (QoreSign / SIWQ) |
| 23–26 | the kiosk key is linked to the venue with the `evm` permission and one allowed call, admitted `dara-1` through the authenticator lane, and was refused when it tried to mint a pass (smart account rules) |
| 27 | the same counters come back through the **QoreChain MCP server**'s `read_contract` |

## The kits this project uses

| Kit | Where | What it does here |
| --- | --- | --- |
| **QoreChain SDK** (`qorechain-sdk`, Python) | `qorepass/chain.py` | hybrid ML-DSA-87 + secp256k1 native transactions, PQC key registration, scoped EVM windows, the authenticator lane |
| **create-qorechain-dapp** | `dapp/` → `web/dapp/` | the viem-wagmi starter, built with the QoreX wallet as the connector |
| **QoreX integrations** (`qorex-rainbowkit`) | `dapp/` | the wallet the dApp recommends and signs with |
| **QoreSeal** (`qorechain-qoreseal`) | `qorepass/sealing.py` | the issuance archive sealed to the issuer's ML-KEM-1024 key |
| **QoreSign** (`qorechain-qoresign`) | `qorepass/receipts.py` | Sign-In-With-QoreChain admission receipts, verified against the chain's key |
| **QoreChain MCP** (`qorechain-mcp`) | `qorepass/mcpread.py` | read-only registry queries through the MCP server's `read_contract` |
| **QoreScan** (`qorescan`) | `docs/cbom.json` | CycloneDX CBOM of the contract + chain, with DORA and NIS2 mappings |

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
  the timestamps. The demo passes are one tap away.
- **Your account**, once QoreX is connected: balance, the EVM authorisation
  window (native-lane REST), and whether the account is a registered issuer
  (`issuerInfo`: pass count, approval nonce, key hash).
- **Scan receipt**: an EIP-191 signature over "pass X scanned by 0x… at time T",
  a classical signature kept as a venue log — the dApp says plainly that it is
  *not* the post-quantum check-in, which needs the holder's ML-DSA-87 signature
  over `checkInMessage(passId, holderKeyHash)`, and points at the SIWQ admission
  receipts in `demo/receipts/` for the venue's own statement.

The build is committed under `web/dapp/` so the URL above works without a server
(it needs no proxy: the registry reads go over the EVM JSON-RPC, which serves
CORS). `dapp/` holds the source; `npm install && npm run build` reproduces
`web/dapp/`.

## What the testnet already did

| | |
| --- | --- |
| Registry | `0x312845b8256cafe2ecc8be7addf54f83a836a88b`, admin `qor1m6x0am3atrl4lwyfvgnjn7m3gr20fnvqlktd3n` |
| Issuer | `qor17as3g4qd04j8tveveqafzwxrqlg6gl257cy3xx` — ML-DSA-87 key registered with proof of possession, then registered as an issuer with its own signature; **ML-KEM-1024 key registered** for QoreSeal |
| Passes | `ada-1` **checked in**, `chen-1` **checked in**, `dara-1` **checked in through the kiosk key**, `boram-1` **revoked**, `eun-1` **valid** (all documents in `demo/passes/`) |
| Issuer signatures | 4627-byte ML-DSA-87 signatures, each over a 275-byte message bound to this chain, this contract and a per-issuer nonce |
| Hybrid-signed native transactions | 19: key registration ×3 (2 ML-DSA-87, 1 ML-KEM), EVM-window opens ×6, funding, three archive anchors, the kiosk link, the kiosk check-in, the kiosk's refused attempt |
| EVM transactions | 15: deploy, issuer registration, 5 passes, 4 check-ins, 1 revoke, 2 forged-pass attempts and 1 duplicate — 6 of them refused on chain (`status: 0`) |
| Refusals, on chain | `AlreadyCheckedIn`, `PassAlreadyRevoked`, `HolderKeyMismatch`, `BadIssuerSignature`, `PassExists`, and the chain's own *authenticator not permitted for this action* |
| Tests | **46 Foundry tests + 7 invariants** (128,000 random calls), **100% lines / statements / branches / functions** |
| Re-verification | `python verify.py` — **27/27**, no keys; `reverify` runs daily in GitHub Actions |

The refusals are the interesting half. `0x51509055…c173` is an attacker who
holds the issuer's classical key, submitting a brand-new pass with a signature
made by a different ML-DSA-87 key: it reverts with `BadIssuerSignature()` and
the pass count does not move.

## The rails beyond the registry

### QoreSeal — the issuance archive nobody else can read

The archive of issued passes is the sensitive half: holder labels, metadata
commitments, the issuer's signature per pass. QorePass seals it before it
anchors it:

1. every pass document goes into one deterministic archive file,
2. the archive is sealed with `qorechain-qoreseal` to the **issuer's ML-KEM-1024
   key** (hybrid X25519 + ML-KEM, envelope bound to the chain, the purpose and an
   AAD of the batch id),
3. only a 32-byte digest of the envelope goes on chain, in the memo of a
   hybrid-signed transaction: `qorepass:seal:v1:9de43ba5…`.

The issuer re-derives the same key from the same mnemonic, so the archive opens
offline years later; anyone else — a quantum computer included — gets an
authentication failure. `demo/sealed/index.json` records the envelope's SHA-256,
length and entry count; `verify.py` recomputes them and compares the anchor
memo.

### QoreSign — an admission receipt the venue cannot fake

A check-in is two statements. *The pass is real* is the registry's job. *This
venue admitted this holder at this time* is the venue's, and QorePass writes it
as a **Sign In With QoreChain** message, signed by the venue's hybrid key pair
and verified against the ML-DSA-87 key its account registered on chain:

```
qorepass.venue wants you to sign in with your QoreChain account:
qor1m6x0am3atrl4lwyfvgnjn7m3gr20fnvqlktd3n
Admit ada-1 (0x1e5e5573…) to QoreChain Demo Day: holder ada, key hash 0x70d7f94d…,
at 2026-11-26T21:10:28Z, registry 0x312845b8…
```

Three receipts live in `demo/receipts/`; their digest is anchored on chain
(`qorepass:receipts:v1:e8926fd9…`). `verify.py` verifies each at its issue time
and refuses an edited timestamp, a re-pointed pass id, and the same receipt 25
hours later.

### Smart account — a door scanner that can do exactly one thing

The venue does not want its door scanner to hold its mnemonic. It links an
Ed25519 kiosk key with the `evm` permission **and a rule naming one call**:

```
allowed_evm_calls = [ 0x312845b8…a88b/0x1ef04ae6 ]   # checkIn(bytes32,bytes,bytes)
```

so a `MsgExecuteEVM` signed by the kiosk key executes as the venue account only
if it calls `checkIn` on this registry. The kiosk has no funds — a relayer pays
the fee and cannot change what the kiosk authorised, because the authorisation
binds target, calldata, value, gas limit and the key's own auth nonce.

It admitted `dara-1` that way (`E468443E…`). Then the same key tried to mint a
pass, and the chain stopped it before the contract ran:
*`a linked key with a spending rule may call 0x3128…a88b with data only if the
rule lists the call in allowed_evm_calls … authenticator not permitted for this
action`* (`F6661812…`). A stolen kiosk key still cannot forge a pass, because
`checkIn` needs the holder's ML-DSA-87 signature.

### QoreChain MCP and QoreScan

`qorepass/mcpread.py` reads the registry through `qorechain-mcp`'s
`read_contract` — the same numbers as `eth_call` — so any MCP client (an editor,
another agent, a judge's tooling) can query it with no credentials. Every tool
in that server is read-only.

`docs/cbom.json` is a CycloneDX 1.6 CBOM of `QorePassRegistry.sol` and the live
chain from `qorescan 0.1.0`: ML-DSA-87 (FIPS 204, category 5) as the signature
the registry requires, Keccak-256, and the two quantum-vulnerable algorithms the
network still carries (ECDSA secp256k1, Ed25519) with their evidence. The same
inventory is mapped to **DORA** RTS 2024/1774 Art. 6 (`docs/DORA-REPORT.md`) and
to the **NIS2** PQC roadmap (`docs/NIS2-REPORT.md`). Reproduce:

```bash
qorescan scan --network testnet --solidity contracts/src --out docs/cbom.json
qorescan report --framework dora --cbom docs/cbom.json --out docs/DORA-REPORT.md
qorescan report --framework nis  --cbom docs/cbom.json --out docs/NIS2-REPORT.md
```

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
  key hash. The pass document carries the readable fields; the archive of them
  is sealed, not published.
- **No transfers.** A pass is not an NFT and cannot be sold; moving it would
  mean re-issuing it to another key, which the issuer must sign for.
- **No admin override of a pass.** The admin can suspend an issuer, but cannot
  mint or un-revoke a pass — those need the issuer's own key.

## Tests

```bash
cd contracts && forge test        # 46 tests + 7 invariants, ~14s
forge coverage --report summary --no-match-coverage "test|mocks"
```

| Suite | What it covers |
| --- | --- |
| `QorePassRegistry.t.sol` | the lifecycle: registration, issuance, check-in, revocation, every refusal, message binding, precompile absence |
| `QorePassRegistryEdge.t.sol` | the paths the happy path never walks: zero admin, an empty key, another algorithm, a key that rotates or disappears under the registry, a precompile that stops answering, double revocation, another issuer's pass |
| `QorePassRegistry.invariant.t.sol` | 256 random sequences × 500 calls: counters equal objects, the nonce equals authorisations, a revoke is final, a check-in time never moves, no pass exists without a holder-key commitment |

Coverage: **100% lines (105/105), statements (148/148), branches (35/35),
functions (19/19)**.

## Daily re-verification (GitHub Actions)

`.github/workflows/daily-verify.yml` runs on every push and once a day:
`forge test`, `forge coverage` against the 100% gate, and `python verify.py`
against the live testnet. It needs no secret — `verify.py` signs nothing — so
the job is the same command a judge runs.

## Quickstart

```bash
git clone https://github.com/dorithesky/qorepass-verify && cd qorepass-verify
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python scripts/bootstrap_keys.py                 # throwaway mnemonics in keys/ (gitignored)
python -m qorepass.cli keygen --holders ada,boram,chen
python -m qorepass.cli fund --to organizer,issuer --uqor 15000000
python -m qorepass.cli register-pqc organizer
python -m qorepass.cli register-pqc issuer
(cd contracts && forge install foundry-rs/forge-std --no-commit && forge build && forge test)

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

# the extra rails
python scripts/onchain_features.py kem             # ML-KEM-1024 key (QoreSeal)
python scripts/onchain_features.py seal            # seal the issuance archive
python scripts/onchain_features.py anchor-seal     # commit its digest
python scripts/onchain_features.py receipts        # SIWQ admission receipts (QoreSign)
python scripts/onchain_features.py anchor-receipts
python scripts/onchain_features.py window          # reopen the EVM windows
python scripts/onchain_features.py link-kiosk      # kiosk key, restricted to checkIn
python scripts/onchain_features.py kiosk-checkin   # admit a pass as the venue
python scripts/onchain_features.py kiosk-refuse    # and prove it cannot mint
python -m qorepass.mcpread state                   # the same numbers over MCP

python -m qorepass.cli evidence                    # docs/EVIDENCE.md, from the chain
python verify.py                                   # 27 read-only checks
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
chain (`verify.py` repeats that comparison for every pass document).

## Repository layout

```
verify.py             read-only re-verification: 27 checks, no keys
contracts/            QorePassRegistry.sol, precompile mocks, 46 tests + invariants
qorepass/             Python package: chain (hybrid txs, windows), evm, passes, cli, evidence,
                      sealing (QoreSeal), receipts (QoreSign/SIWQ), kiosk (smart account), mcpread (MCP)
scripts/              key bootstrap, encoder check, refusal explainer, on-chain features, video
web/index.html        the verifier dashboard (no dependencies, reads the chain over JSON-RPC)
web/dapp/             the built create-qorechain-dapp + QoreX wallet dApp
demo/passes/*.json    the five issued pass documents, public fields only
demo/sealed/          the issuance archive, sealed to the issuer's ML-KEM key
demo/receipts/        the SIWQ admission receipts
demo/features.json    the extra rails: keys, envelopes, receipts, kiosk — with their tx hashes
demo/journal.jsonl    every action this run took, with tx hashes and revert reasons
docs/EVIDENCE.md      generated from the chain
docs/cbom.json        QoreScan CycloneDX CBOM (+ DORA and NIS2 reports beside it)
docs/cover.png        16:9 cover
```

## How it was built

The on-chain side is QoreChain's Python SDK (`qorechain-sdk>=0.15.0`: hybrid
native signatures, EVM windows, PQC key registration, the authenticator lane)
and Foundry for Solidity. The dApp is the official `create-qorechain-dapp`
viem-wagmi starter with the QoreX wallet. The extra rails are three more kits
(QoreSeal, QoreSign, QoreChain MCP) plus QoreScan for the inventory. The AI
workflow behind the build — including what it got wrong — is documented in
[`AI_USAGE.md`](AI_USAGE.md).

## Licence

Apache-2.0. Testnet only: every key in this repository's history is a throwaway
test key with no value.
