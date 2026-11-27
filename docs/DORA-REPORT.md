# Cryptographic inventory mapped to DORA RTS on ICT risk management, Article 6

> **Disclaimer.** QoreScan output is an inventory aid. It is not a certification, an audit or a legal opinion, and it does not establish conformity with any regulation or standard. The mapping below shows where the inventory can serve as input; whether an organisation meets a requirement depends on facts outside the scan and is for the organisation and its advisers to assess.

| | |
|---|---|
| CBOM | `urn:uuid:b96243d5-e0f1-5e63-be82-2e0ec67ca27a` |
| Generated | 2026-11-27T13:48:28Z by qorescan 0.1.0 |
| Chain | `qorechain-diana` |
| Scanned | chain, solidity |

## Framework mapping

| RTS 2024/1774 | Requirement (paraphrased) | What this inventory provides | Status |
|---|---|---|---|
| Art. 6(1) | Develop, document and implement a policy on encryption and cryptographic controls. | Inventory input for the policy. | _To be completed._ |
| Art. 6(2)(a) | Rules for encrypting data at rest and in transit. | No transport was scanned. Data at rest is not scanned. | In transit: input; at rest _to be completed._ |
| Art. 6(2)(c) | Rules for encrypting internal network connections and traffic with external parties. | P2P transport and TLS endpoint records; listeners without TLS are listed under scan notes. | Input for the scanned scope |
| Art. 6(2)(d) | Cryptographic key management in line with Article 7. | 1 key record (types and public keys only). | Key lifecycle _to be completed._ |
| Art. 6(3) | Criteria for selecting cryptographic techniques, considering leading practices and standards. | Each algorithm stated against FIPS 203/204/205 and NIST IR 8547 below. | Input |
| Art. 6(4) | Update or change cryptographic technology on the basis of developments in cryptanalysis. | Scanned evidence: native-lane hybrid signature mode required; algorithm migration dual-signature period of 1000000 blocks (module parameter). | Evidence listed; assessment _to be completed._ |
| Art. 6(5) | Record mitigation and monitoring measures adopted under paragraphs 3 and 4, with reasons. | Nothing: organisational record. | _To be completed._ |

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

- Commission Delegated Regulation (EU) 2024/1774 of 13 March 2024 (regulatory technical standards on the ICT risk management framework under Regulation (EU) 2022/2554, DORA), Article 6: <https://eur-lex.europa.eu/eli/reg_del/2024/1774/oj>
- NIST IR 8547, "Transition to Post-Quantum Cryptography Standards", final, October 2026: <https://doi.org/10.6028/NIST.IR.8547>
- FIPS 203, Module-Lattice-Based Key-Encapsulation Mechanism Standard: <https://csrc.nist.gov/pubs/fips/203/final>
- FIPS 204, Module-Lattice-Based Digital Signature Standard: <https://csrc.nist.gov/pubs/fips/204/final>
- FIPS 205, Stateless Hash-Based Digital Signature Standard: <https://csrc.nist.gov/pubs/fips/205/final>

The framework rows paraphrase the source documents; read the sources for the authoritative wording.
