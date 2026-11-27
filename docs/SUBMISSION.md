# Submission record — Build Before Q-Day, Quantum Pass

| | |
| --- | --- |
| Project page | <https://build.qorechain.io/ko/p/qorepass> (slug `qorepass`) |
| Category | Quantum Pass |
| Team | @dorithesky (solo), public name `pickle-scout` |
| Licence | Apache-2.0 |
| Repository | <https://github.com/dorithesky/qorepass-verify> |
| Live verifier | <https://dorithesky.github.io/qorepass-verify/> |
| QoreX dApp | <https://dorithesky.github.io/qorepass-verify/web/dapp/> |
| Video | `demo/qorepass-demo.mp4` (152 s) · <https://dorithesky.github.io/qorepass-verify/demo/qorepass-demo.mp4> |
| Cover | `docs/cover.png` (2400 × 1350) |
| Network | `qorechain-diana`, EVM chain id 9800 |
| Testnet addresses | `qor1m6x0am3atrl4lwyfvgnjn7m3gr20fnvqlktd3n` (organiser/venue), `qor17as3g4qd04j8tveveqafzwxrqlg6gl257cy3xx` (issuer) |
| Registry | `0x312845b8256cafe2ecc8be7addf54f83a836a88b` (deploy tx `0x834f7228…f231`, block 10810247) |
| Kits | QoreChain SDK (Python) · create-qorechain-dapp · QoreX integrations · QoreSeal · QoreSign · QoreChain MCP · QoreScan |
| Network features | hybrid ML-DSA-87 transactions · PQC key registration with proof of possession · EVM window (incl. scoped) · PQC signature verification in Solidity · PQC key status in Solidity · QoreSeal and the key registry · smart account and spending rules · MCP server · Sign In With QoreChain · QoreScan |
| Special awards | AI-Native (AI_USAGE.md) · Regional: 대한민국 (Asia-Pacific) |
| Ship Weeks badges | first hybrid transaction · first contract with a PQC check · first QoreSeal key (issuer's ML-KEM-1024 registration) |

## What a judge can run, with no key

```bash
pip install -r requirements.txt
python verify.py        # 27 checks, read-only, ~30 s
```

`verify.py` compares the deployed bytecode with `contracts/out`, replays all 34
journal entries against the chain (15 EVM + 19 native), reproduces five
refusals with `eth_call`, verifies every pass document's 4627-byte ML-DSA-87
signature offline, checks the sealed archive against its anchor memo, verifies
the three SIWQ receipts against the venue's on-chain key, and reads the kiosk
key's link and its refused mint attempt. No private key is read; nothing is
signed.

## What changed in the second pass (2026-11-27)

| | first submission | now |
| --- | --- | --- |
| Kits | 1 verified (SDK) + 1 declared (create-qorechain-dapp) | 7 used: SDK, create-qorechain-dapp, QoreX, **QoreSeal**, **QoreSign**, **MCP**, **QoreScan** |
| Features verified on chain | 3 | 6 (+ QoreSeal key & archive, smart-account kiosk key, SIWQ receipts, MCP reads, QoreScan inventory) |
| Passes | 3 | 5 (`dara-1` admitted through the kiosk key, `eun-1` valid) |
| Tests | 28 | 46 + 7 invariants, 100% lines/statements/branches/functions |
| Re-verification | none | `verify.py` 27/27, daily in GitHub Actions |
| Compliance | none | CBOM + DORA RTS Art. 6 + NIS2 roadmap mappings |

## What the submission rests on

`docs/EVIDENCE.md` — regenerated from the chain, not transcribed: contract and
deploy tx, both accounts, the issuer's registered ML-DSA-87 and ML-KEM-1024
keys, the five passes and their states, all 34 transactions, the six refusals
with the contract's own custom errors, and the seven extra rails with their
anchor transactions.
