# Submission record — Build Before Q-Day, Quantum Pass

| | |
| --- | --- |
| Project page | <https://build.qorechain.io/ko/p/qorepass> (slug `qorepass`) |
| Category | Quantum Pass |
| Team | @dorithesky (solo), public name `pickle-scout` |
| Licence | Apache-2.0 |
| Repository | <https://github.com/dorithesky/qorepass-verify> |
| Live verifier | <https://dorithesky.github.io/qorepass-verify/> |
| Video | `demo/qorepass-demo.mp4` (107 s) · <https://dorithesky.github.io/qorepass-verify/demo/qorepass-demo.mp4> |
| Cover | `docs/cover.png` (2400 × 1350) |
| Network | `qorechain-diana`, EVM chain id 9800 |
| Testnet addresses | `qor1m6x0am3atrl4lwyfvgnjn7m3gr20fnvqlktd3n` (organiser/venue), `qor17as3g4qd04j8tveveqafzwxrqlg6gl257cy3xx` (issuer) |
| Declared kits | QoreChain SDK — Python |
| Network features declared | hybrid ML-DSA-87 transactions · PQC key registration with proof of possession · EVM window (incl. scoped) · PQC signature verification in Solidity · PQC key status in Solidity |
| Special awards | AI-Native (AI_USAGE.md) · Regional: 대한민국 (Asia-Pacific) |
| Ship Weeks badges | first hybrid transaction · first contract with a PQC check |

## Automatic verification (site, 2026-11-27 06:33 KST)

- QoreChain SDK: verified from the repository's dependency file (1 of 1 declared).
- On-chain: `qor1m6x0am3…` confirmed with 11 transactions, `qor17as3g4q…` with 9 —
  EVM window, hybrid ML-DSA-87 transactions and PQC key registration with proof
  of possession are all verified against the chain, not just declared.
- Solidity PQC signature verification and PQC key status show as *declared*: the
  registry reads them on every call (`docs/EVIDENCE.md` has the transactions),
  but the site's static check does not mark them verified.

## What the submission rests on

`docs/EVIDENCE.md` — regenerated from the chain, not transcribed: contract and
deploy tx, both accounts, the issuer's registered key hash, the three passes and
their states, all 22 transactions, and the five refusals with the contract's own
custom errors.
