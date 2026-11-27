# Cryptographic inventory mapped to EU NIS Cooperation Group PQC roadmap

> **Disclaimer.** QoreScan output is an inventory aid. It is not a certification, an audit or a legal opinion, and it does not establish conformity with any regulation or standard. The mapping below shows where the inventory can serve as input; whether an organisation meets a requirement depends on facts outside the scan and is for the organisation and its advisers to assess.

| | |
|---|---|
| CBOM | `urn:uuid:b96243d5-e0f1-5e63-be82-2e0ec67ca27a` |
| Generated | 2026-11-27T13:48:28Z by qorescan 0.1.0 |
| Chain | `qorechain-diana` |
| Scanned | chain, solidity |

## Framework mapping

| Roadmap item | Expectation (paraphrased) | What this inventory provides | Status |
|---|---|---|---|
| First Steps: cryptographic asset management | Create and maintain inventories of assets that perform or rely on cryptographic operations; a standardised format such as CBOM is recommended. | CBOM with 4 algorithms (2 quantum-vulnerable, 1 post-quantum, 0 hybrid), 0 protocols, 0 certificates, 1 key record, in CycloneDX 1.6. | Input for the scanned scope |
| Milestone 1 (31.12.2026) | Member States: First Steps implemented, national roadmaps in place, transition planning and pilots for high- and medium-risk use cases started. | Nothing: planning measure. | _To be completed._ |
| Milestone 2 (31.12.2030) | Transition of high-risk use cases completed; post-quantum software and firmware upgrades enabled by default. | 2 quantum-vulnerable algorithms listed below with their evidence. | Risk classification per use case _to be completed._ |
| Milestone 3 (31.12.2035) | Transition of medium-risk use cases completed; low-risk use cases as far as feasible. | Same list; NIST IR 8547 disallows the listed families after 2035. | _To be completed._ |
| Cryptographic agility | Support crypto-agility and an upgrade path when products are developed. | Scanned evidence: native-lane hybrid signature mode required; algorithm migration dual-signature period of 1000000 blocks (module parameter). | Evidence listed; assessment _to be completed._ |

## Summary

| Classification | Algorithms |
|---|---|
| post-quantum | 1: ML-DSA-87 |
| quantum-vulnerable | 2: ECDSA secp256k1, Ed25519 |
| symmetric | 1: Keccak-256 |

NIST IR 8547 deprecates quantum-vulnerable public-key algorithms (RSA, ECDSA, EdDSA, finite-field and elliptic-curve DH) after 2030 and disallows them under NIST standards after 2035; applications may be given earlier dates.

## Algorithms and status

| Algorithm | Primitive | Parameter set | NIST category | FIPS 203/204/205 | NIST IR 8547 | Evidence |
|---|---|---|---|---|---|---|
| ECDSA secp256k1 | signature | - | 0 | not covered (quantum-vulnerable) | Deprecated after 2030, disallowed after 2035 (NIST IR 8547) | `https://api-testnet.qore.host/cosmos/evm/vm/v1/params` (+1 more) |
| Ed25519 | signature | - | 0 | not covered (quantum-vulnerable) | Deprecated after 2030, disallowed after 2035 (NIST IR 8547) | `https://api-testnet.qore.host/cosmos/base/tendermint/v1beta1/validatorsets/latest?pagination.limit=1000` |
| ML-DSA-87 | signature | 87 | 5 | FIPS 204 | Not scheduled for deprecation by NIST IR 8547 | `QorePassRegistry.sol:33` (+3 more) |
| Keccak-256 | hash | 256 | not defined | not applicable (symmetric or hash) | Not a NIST-standardised algorithm; not scheduled by NIST IR 8547 | `QorePassRegistry.sol:42` (+11 more) |

## Keys

QoreScan records public keys and key types only; it never reads private key values.

| Key | Type | Algorithm | Count | Evidence |
|---|---|---|---|---|
| Active validator consensus public keys (Ed25519) | public-key | Ed25519 | 4 | `https://api-testnet.qore.host/cosmos/base/tendermint/v1beta1/validatorsets/latest?pagination.limit=1000` |

## Scanned facts

| Fact | Value |
|---|---|
| `chain:consensus-engine-version` | 0.38.26 |
| `chain:evm:active-precompile` | crossVmBridge (0x0000000000000000000000000000000000000901); rlConsensusParams (0x0000000000000000000000000000000000000C01); pqcVerify (0x0000000000000000000000000000000000000a01); pqcKeyStatus (0x0000000000000000000000000000000000000a02) |
| `chain:id` | qorechain-diana |
| `chain:network` | testnet |
| `chain:pqc:allow-classical-fallback` | false |
| `chain:pqc:default-migration-blocks` | 1000000 |
| `chain:pqc:hybrid-signature-mode` | required |
| `chain:pqc:min-security-level` | 5 |
| `chain:pqc:pqc-primary` | true |
| `chain:protocol-feature` | pqc-sign-bytes-v2; evm-pqc-authorisation-window; pqc-ecdsa-pubkey-validation; pqc-keyed-account-maintenance-hybrid; pqc-registration-integrity; pqc-rotation-replay-guard; pqc-algorithm-governance-guards; pqc-hybrid-single-extension; pqc-keyless-extension-closed; evm-pqc-window-targets; pqc-possession-flag; pqc-kem-registry; pqc-rotate-key-size-check; pqc-verify-once-per-signer; pqc-multisig; pqc-verify-gas-calibrated; pqc-consent-authz-limiter; pqc-consent-outer-signer; pqc-rotation-ends-evm-consent; pqc-degenerate-key-refused; svm-pqc-key-lane-gated; pqc-registration-ends-evm-consent; pqc-consent-own-message; svm-pqc-key-for-wallets; svm-pqc-authorisation-window; qcb-pqc-submitter; pqc-key-change-clears-evm-delegation; pqc-svm-window-key-proof; pqc-registration-ends-svm-window; pqc-hybrid-embedded-key-degenerate; qcb-pqc-submitter-own-message; pqc-key-registration-own-message; pqc-verify-empty-message |
| `chain:protocol-features` | 353 enabled at height 10852356 (33 PQC-related listed) |
| `chain:rest` | https://api-testnet.qore.host |

## Sources

- EU PQC Workstream of the NIS Cooperation Group, "A Coordinated Implementation Roadmap for the Transition to Post-Quantum Cryptography", Part 1, version 1.1, 11 June 2025: <https://digital-strategy.ec.europa.eu/en/library/coordinated-implementation-roadmap-transition-post-quantum-cryptography>
- NIST IR 8547, "Transition to Post-Quantum Cryptography Standards", final, October 2026: <https://doi.org/10.6028/NIST.IR.8547>
- FIPS 203, Module-Lattice-Based Key-Encapsulation Mechanism Standard: <https://csrc.nist.gov/pubs/fips/203/final>
- FIPS 204, Module-Lattice-Based Digital Signature Standard: <https://csrc.nist.gov/pubs/fips/204/final>
- FIPS 205, Stateless Hash-Based Digital Signature Standard: <https://csrc.nist.gov/pubs/fips/205/final>

The framework rows paraphrase the source documents; read the sources for the authoritative wording.
