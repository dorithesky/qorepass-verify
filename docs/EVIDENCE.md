# Evidence — what `qorechain-diana` actually recorded

Generated 2026-11-26 21:13 UTC by `python -m qorepass.cli evidence` from the chain itself. EVM chain id 9800. Open any hash at https://explore.qore.network/tx/<hash> with the explorer switched to **Testnet**.

## The contract

- registry: `0x312845b8256cafe2ecc8be7addf54f83a836a88b`
- deploy tx: [`0x834f722842fcaa41363de7b233b30c4e772f8ffc4752cf3e2170eb36f466f231`](https://explore.qore.network/tx/0x834f722842fcaa41363de7b233b30c4e772f8ffc4752cf3e2170eb36f466f231) (block 10810247)
- admin: `0xdE8cfeeE3D58FF5FB889622729fb7140D4F4CD80` / `qor1m6x0am3atrl4lwyfvgnjn7m3gr20fnvqlktd3n`

## Accounts

| role | native | EVM | QOR | ML-DSA-87 key on chain |
| --- | --- | --- | ---: | :---: |
| organizer (venue / admin) | `qor1m6x0am3atrl4lwyfvgnjn7m3gr20fnvqlktd3n` | `0xdE8cfeeE3D58FF5FB889622729fb7140D4F4CD80` | 13.365 | yes |
| issuer (issuer) | `qor17as3g4qd04j8tveveqafzwxrqlg6gl257cy3xx` | `0xf76114540D7D6475B32cc83A9138C307D1a47d54` | 14.154 | yes |

The demo holders (attendees) have no QoreChain account at all: a pass binds an
ML-DSA-87 **public key**, so an attendee needs a key, not a wallet, and the
venue pays the gas for the check-in.

## Registering the issuer's key (the chain's own view)

- issuer pubkey hash on chain: `0x76d0b988b0633d656d122dfd2f49d53358e9a34685abc8fd08b608f0256a9613`
- issuer ML-DSA-87 key registered for the account: **True**, 2592 bytes
- registered at 2026-11-26 21:09 UTC, active **True**, passes issued **3**, approval nonce **4**
- name hash `0xa8e8a0012b697772b4c7a911fd1fda4e…`

## Passes

| pass | holder | event | valid until | state on chain | checked in |
| --- | --- | --- | --- | --- | --- |
| `ada-1` | ada | QoreChain Demo Day | 2026-12-03 21:09 UTC | **CHECKED_IN** | 2026-11-26 21:10 UTC |
| `boram-1` | boram | QoreChain Demo Day | 2026-12-03 21:10 UTC | **REVOKED** | — |
| `chen-1` | chen | QoreChain Demo Day | 2026-12-03 21:10 UTC | **CHECKED_IN** | 2026-11-26 21:11 UTC |

## Transactions

| # | action | by | result | tx | note |
| ---: | --- | --- | --- | --- | --- |
| 1 | fund | funder | — | [`F206F0CD0A8A08F5550C…`](https://explore.qore.network/tx/F206F0CD0A8A08F5550C196B14A7D1DE9A8E55BB2A17E7B0FD1CDED9B9479C4A) |  |
| 2 | fund | funder | — | [`A65DBE2FEE4B21094A98…`](https://explore.qore.network/tx/A65DBE2FEE4B21094A9830282E2321E0FB8C9838EE442BFAA154A25B9460365C) |  |
| 3 | register-pqc | organizer | — | [`0161C3B1CF4E04A37551…`](https://explore.qore.network/tx/0161C3B1CF4E04A375510AB8EA56679EDE4E543B4081F0FCAACBBEE52313D48F) |  |
| 4 | register-pqc | issuer | — | [`1C854A3E9436DBB4DFE6…`](https://explore.qore.network/tx/1C854A3E9436DBB4DFE662B19598713E8585ABC94DFAF234E23E0B8FA9D18B20) |  |
| 5 | open-window | organizer | — | [`D99080ED523FC7F7EA4D…`](https://explore.qore.network/tx/D99080ED523FC7F7EA4D5069D757574BEF4C6EE6418E6F1BA12E39C420FA975E) | blocks=100 txs=1 targets=[] |
| 6 | open-window | organizer | — | [`15B499D9DA1E7C5F1A78…`](https://explore.qore.network/tx/15B499D9DA1E7C5F1A78EDEC90AF481A461F02B70AEA12C25E7D1637D39DDBAC) | blocks=100 txs=1 targets=[] |
| 7 | deploy | organizer | — | [`0x834f722842fcaa4136…`](https://explore.qore.network/tx/0x834f722842fcaa41363de7b233b30c4e772f8ffc4752cf3e2170eb36f466f231) | 0x312845b8256cafe2ecc8be7addf54f83a836a88b |
| 8 | open-window | issuer | — | [`33C1AACDD2BBFB1AED09…`](https://explore.qore.network/tx/33C1AACDD2BBFB1AED09F0B7623FFD5440EA5845CC823415505F1EC410D2D3E3) | blocks=3000 txs=12 targets=['0x312845b8256cafe2ecc8be7addf54f83a836a88b'] |
| 9 | open-window | organizer | — | [`8080194914971F01C04B…`](https://explore.qore.network/tx/8080194914971F01C04BFCBEBD61B5B39DD789EB6982AF414A2CA1D457652062) | blocks=3000 txs=12 targets=['0x312845b8256cafe2ecc8be7addf54f83a836a88b'] |
| 10 | register-issuer | issuer | ok | [`0xcd4412c48a651fe4c3…`](https://explore.qore.network/tx/0xcd4412c48a651fe4c3fea18ed71fa02a00c40f09074764527ceffce479f23a75) | QoreChain Demo Day · signed message 147B, signature 4627B |
| 11 | issue | issuer | ok | [`0x46cfd9f73b4b0cd5d9…`](https://explore.qore.network/tx/0x46cfd9f73b4b0cd5d980c06fd062041c29181d6ae814a1a4c09e6c45ab579aa4) | QoreChain Demo Day · nonce 0 · sig 4627B |
| 12 | issue | issuer | ok | [`0x6819d8195646c290b7…`](https://explore.qore.network/tx/0x6819d8195646c290b73efb4cc7e2647a6bbb92b04032bce963216c0cb6d79e3b) | QoreChain Demo Day · nonce 1 · sig 4627B |
| 13 | issue | issuer | ok | [`0x850184a4b68d62d194…`](https://explore.qore.network/tx/0x850184a4b68d62d1947c9b5991b785e7d98e202789c06ea1393347f9242379d9) | QoreChain Demo Day · nonce 2 · sig 4627B |
| 14 | checkin | organizer | ok | [`0x76eb514be082710771…`](https://explore.qore.network/tx/0x76eb514be08271077184e797131ba1d04949d2f7f7d5bda99554ba941c311f94) | holder signature over 159B message, sig 4627B, state CHECKED_IN |
| 15 | checkin | organizer | **refused** | [`0xf60a9b8c5115e101e3…`](https://explore.qore.network/tx/0xf60a9b8c5115e101e35a549c486df86b595e4d6e8fc40f1817f9a8e5127e253f) | **AlreadyCheckedIn(0x1e5e5573eea8…, 1795727428)** — holder signature over 159B message, sig 4627B, state CHECKED_IN |
| 16 | revoke | issuer | ok | [`0xf7cee507d9bc616ab4…`](https://explore.qore.network/tx/0xf7cee507d9bc616ab4dbc5a88c9edf23dbf5ae49cd359febff93a76619ceda1d) | reason 'refunded after transfer' · nonce 3 · state REVOKED |
| 17 | checkin | organizer | **refused** | [`0x3b756500f31fbe9484…`](https://explore.qore.network/tx/0x3b756500f31fbe948401b82aeacdee0e0819434ffb05bb8296aa06fa58da0585) | **PassAlreadyRevoked(0x81f49c48cfe4…)** — holder signature over 159B message, sig 4627B, state REVOKED |
| 18 | checkin | organizer | **refused** | [`0x53c9fa6c7d5618d772…`](https://explore.qore.network/tx/0x53c9fa6c7d5618d772785b0519e9c567f3c7a9483ba58d6a1bba812499ce080f) | **HolderKeyMismatch()** — holder signature over 159B message, sig 4627B, state VALID |
| 19 | forged-issue | attacker (issuer classical key) | **refused** | [`0x314383f6b0c786c962…`](https://explore.qore.network/tx/0x314383f6b0c786c9622759198613ad40c278c8e39d3a2a2ff1b5818842d798e7) | **PassExists(0xcc1fb73a375a…)** — re-issue of an existing pass id with a forged signature (refused before the signature check) |
| 20 | checkin | organizer | ok | [`0xf5fa740b5e0a5650f9…`](https://explore.qore.network/tx/0xf5fa740b5e0a5650f9b756d0c6a7dc713b34bc8be3e3cf5870bd4999a910f0e6) | holder signature over 159B message, sig 4627B, state CHECKED_IN |
| 21 | anchor | organizer | ok | [`FC745BE4370ACEFC1D48…`](https://explore.qore.network/tx/FC745BE4370ACEFC1D48F98F6FC32681269DC7FBA51781BAF19F6573BA54C3D3) | qorepass:v1:c07f8bf4d29fc4bf391a4f433fa024b451692fed79095c335de3b649772d203f |
| 22 | forged-issue | attacker holding the issuer's classical key | **refused** | [`0x5150905522164d2e4c…`](https://explore.qore.network/tx/0x5150905522164d2e4c3a4aa5a122ac6d0c03d752424f5030f51cf7692489c173) | **BadIssuerSignature()** — new pass id, signature made with a key that is not the issuer's ML-DSA-87 key |

## Refusals, on chain

A refused call still mines a transaction (`status: 0`) and reverts with the
contract's own error. These are the ones in the run above:

- `checkin` on `ada-1`: [`0xf60a9b8c5115e101e35a549c486df86b595e4d6e8fc40f1817f9a8e5127e253f`](https://explore.qore.network/tx/0xf60a9b8c5115e101e35a549c486df86b595e4d6e8fc40f1817f9a8e5127e253f) — **AlreadyCheckedIn(0x1e5e5573eea8…, 1795727428)** (holder signature over 159B message, sig 4627B, state CHECKED_IN)
- `checkin` on `boram-1`: [`0x3b756500f31fbe948401b82aeacdee0e0819434ffb05bb8296aa06fa58da0585`](https://explore.qore.network/tx/0x3b756500f31fbe948401b82aeacdee0e0819434ffb05bb8296aa06fa58da0585) — **PassAlreadyRevoked(0x81f49c48cfe4…)** (holder signature over 159B message, sig 4627B, state REVOKED)
- `checkin` on `chen-1`: [`0x53c9fa6c7d5618d772785b0519e9c567f3c7a9483ba58d6a1bba812499ce080f`](https://explore.qore.network/tx/0x53c9fa6c7d5618d772785b0519e9c567f3c7a9483ba58d6a1bba812499ce080f) — **HolderKeyMismatch()** (holder signature over 159B message, sig 4627B, state VALID)
- `forged-issue` on `chen-1`: [`0x314383f6b0c786c9622759198613ad40c278c8e39d3a2a2ff1b5818842d798e7`](https://explore.qore.network/tx/0x314383f6b0c786c9622759198613ad40c278c8e39d3a2a2ff1b5818842d798e7) — **PassExists(0xcc1fb73a375a…)** (re-issue of an existing pass id with a forged signature (refused before the signature check))
- `forged-issue` on `0xc77b825217adff…`: [`0x5150905522164d2e4c3a4aa5a122ac6d0c03d752424f5030f51cf7692489c173`](https://explore.qore.network/tx/0x5150905522164d2e4c3a4aa5a122ac6d0c03d752424f5030f51cf7692489c173) — **BadIssuerSignature()** (new pass id, signature made with a key that is not the issuer's ML-DSA-87 key)

## How to check it yourself

```bash
# the registry's totals (passState is 0 unknown, 1 valid, 2 checked in, 3 expired, 4 revoked)
curl -s https://api-testnet.qore.host/cosmos/tx/v1beta1/txs/<hash> | jq .tx_response.code, .tx_response.raw_log

# the same reads the web verifier does, straight from the EVM lane
curl -s -X POST https://evm-testnet.qore.host -H "content-type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":"0x312845b8256cafe2ecc8be7addf54f83a836a88b",
  "data":"0x..."},"latest"]}'
```

The pass documents in `demo/passes/` carry the issuer's 4627-byte ML-DSA-87
signature; `python -m qorepass.cli verify --pass <name>` recomputes the message
from the document and verifies that signature offline, with no chain access.

