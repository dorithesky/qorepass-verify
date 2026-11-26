// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

/// @notice Test-only stand-ins for QoreChain's post-quantum precompiles.
///
///         `forge test` etches `MockPQCVerify` at `0x…0a01` and
///         `MockPQCKeys` at `0x…0a02`, so the registry's logic — nonces,
///         state transitions, key binding, replay refusal — can be exercised
///         without a live chain. On `qorechain-diana` the node answers both
///         addresses itself.
///
///         A "signature" here is `0x01 || message`. That keeps the mock honest
///         about the property the registry relies on: a signature is valid for
///         exactly one message, so a signature made for one pass cannot issue
///         another.
contract MockPQCVerify {
    function pqcVerify(bytes calldata, bytes calldata signature, bytes calldata message)
        external
        pure
        returns (bool)
    {
        if (signature.length < 2 || signature[0] != 0x01) return false;
        return keccak256(signature[1:]) == keccak256(message);
    }
}

contract MockPQCKeys {
    struct Key {
        bool registered;
        uint8 algorithmId;
        bytes pubkey;
        bool proven;
    }

    mapping(address => Key) internal _keys;

    function setKey(address account, uint8 algorithmId, bytes calldata pubkey, bool proven) external {
        _keys[account] = Key({registered: true, algorithmId: algorithmId, pubkey: pubkey, proven: proven});
    }

    function clearKey(address account) external {
        delete _keys[account];
    }

    function pqcKeyStatus(address account)
        external
        view
        returns (bool registered, uint8 algorithmId, bytes memory pubkey, bool possessionProven)
    {
        Key storage k = _keys[account];
        return (k.registered, k.algorithmId, k.pubkey, k.proven);
    }
}
