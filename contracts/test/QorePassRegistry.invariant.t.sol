// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {StdInvariant} from "forge-std/StdInvariant.sol";
import {QorePassRegistry} from "../src/QorePassRegistry.sol";
import {MockPQCVerify, MockPQCKeys} from "../src/mocks/MockPQC.sol";

/// @notice Random sequences of issue / check-in / revoke / suspend, then the
///         properties that must hold whatever order they arrive in.
///
///         The registry's own counters are the claim; the handler's ghost
///         bookkeeping is the independent count. If the two ever disagree, a
///         pass was counted twice, counted without existing, or a state
///         transition went somewhere it should not.
contract QorePassHandler is Test {
    QorePassRegistry public immutable registry;
    address public immutable issuer;
    address public immutable admin;
    address public constant VENUE = address(0x7E9E);

    bytes public issuerKey = "issuer-ml-dsa-87-public-key";
    bytes public holderKey = "handler-holder-key";
    bytes public otherHolderKey = "handler-someone-else";

    bytes32[] public ids;

    // ghosts: what the handler itself saw succeed
    uint32 public ghostIssued;
    uint32 public ghostCheckedIn;
    uint32 public ghostRevoked;

    // ghosts: facts that must never be contradicted
    mapping(bytes32 => bool) public everRevoked;
    mapping(bytes32 => uint64) public firstCheckedInAt;

    constructor(QorePassRegistry registry_, address issuer_, address admin_) {
        registry = registry_;
        issuer = issuer_;
        admin = admin_;
    }

    function sign(bytes memory message) internal pure returns (bytes memory) {
        return abi.encodePacked(bytes1(0x01), message);
    }

    function idAt(uint256 seed) public view returns (bytes32) {
        if (ids.length == 0) return bytes32(uint256(0xdead));
        return ids[seed % ids.length];
    }

    function issue(uint256 seed, uint64 ttl) public {
        bytes32 passId = keccak256(abi.encodePacked("pass", seed, ids.length));
        uint64 validUntil = uint64(block.timestamp + (ttl % 30 days) + 1);
        bytes memory message =
            registry.issuePassMessage(issuer, passId, address(0), keccak256("event"), keccak256("meta"), keccak256(holderKey), validUntil, registry.issuerNonce(issuer));
        try registry.issuePass(passId, address(0), keccak256("event"), keccak256("meta"), keccak256(holderKey), validUntil, sign(message))
        {
            ids.push(passId);
            ghostIssued += 1;
        } catch {}
    }

    function checkIn(uint256 seed) public {
        bytes32 passId = idAt(seed);
        bytes memory message = registry.checkInMessage(passId, keccak256(holderKey));
        try registry.checkIn(passId, holderKey, sign(message)) {
            ghostCheckedIn += 1;
            if (firstCheckedInAt[passId] == 0) firstCheckedInAt[passId] = uint64(block.timestamp);
        } catch {}
    }

    function checkInWithAnotherKey(uint256 seed) public {
        bytes32 passId = idAt(seed);
        bytes memory message = registry.checkInMessage(passId, keccak256(holderKey));
        try registry.checkIn(passId, otherHolderKey, sign(message)) {} catch {}
    }

    function revoke(uint256 seed) public {
        bytes32 passId = idAt(seed);
        uint32 nonce = registry.issuerNonce(issuer);
        bytes memory message = registry.revokePassMessage(issuer, passId, keccak256("refunded"), nonce);
        try registry.revokePass(passId, keccak256("refunded"), sign(message)) {
            ghostRevoked += 1;
            everRevoked[passId] = true;
        } catch {}
    }

    function forgeIssue(uint256 seed) public {
        // the Q-Day attempt: the right message, a signature from another key
        bytes32 passId = keccak256(abi.encodePacked("forged", seed));
        uint64 validUntil = uint64(block.timestamp + 1 days);
        bytes memory message =
            registry.issuePassMessage(issuer, passId, address(0), keccak256("event"), keccak256("meta"), keccak256(holderKey), validUntil, registry.issuerNonce(issuer));
        try registry.issuePass(passId, address(0), keccak256("event"), keccak256("meta"), keccak256(holderKey), validUntil, sign("attacker"))
        {} catch {}
        // and the honest signature must still work afterwards (nothing poisoned)
        try registry.issuePass(passId, address(0), keccak256("event"), keccak256("meta"), keccak256(holderKey), validUntil, sign(message))
        {
            ids.push(passId);
            ghostIssued += 1;
        } catch {}
    }

    function suspend(bool on) public {
        try registry.setIssuerActive(issuer, !on) {} catch {}
        try registry.setIssuerActive(issuer, on) {} catch {}
    }

    function idsLength() external view returns (uint256) {
        return ids.length;
    }
}

contract QorePassInvariantTest is StdInvariant, Test {
    QorePassRegistry internal registry;
    QorePassHandler internal handler;

    address internal constant PQC_VERIFY = 0x0000000000000000000000000000000000000a01;
    address internal constant PQC_KEYS = 0x0000000000000000000000000000000000000a02;

    address internal admin = address(0xA11CE);
    address internal issuer = address(0x1550E);

    function setUp() public {
        vm.etch(PQC_VERIFY, address(new MockPQCVerify()).code);
        vm.etch(PQC_KEYS, address(new MockPQCKeys()).code);
        registry = new QorePassRegistry(admin);
        MockPQCKeys(PQC_KEYS).setKey(issuer, 1, "issuer-ml-dsa-87-public-key", true);

        bytes memory message = registry.registerIssuerMessage(issuer, keccak256("QoreChain Demo Day"));
        vm.prank(issuer);
        registry.registerIssuer(
            "issuer-ml-dsa-87-public-key", abi.encodePacked(bytes1(0x01), message), "QoreChain Demo Day"
        );

        handler = new QorePassHandler(registry, issuer, admin);
        targetContract(address(handler));
        bytes4[] memory selectors = new bytes4[](6);
        selectors[0] = QorePassHandler.issue.selector;
        selectors[1] = QorePassHandler.checkIn.selector;
        selectors[2] = QorePassHandler.checkInWithAnotherKey.selector;
        selectors[3] = QorePassHandler.revoke.selector;
        selectors[4] = QorePassHandler.forgeIssue.selector;
        selectors[5] = QorePassHandler.suspend.selector;
        targetSelector(FuzzSelector({addr: address(handler), selectors: selectors}));
    }

    /// @dev The counter equals the objects: no pass is counted that does not exist.
    function invariant_issuedCountMatchesPasses() public view {
        uint256 existing;
        uint256 n = handler.idsLength();
        for (uint256 i = 0; i < n; i++) {
            (,,,,,,, , QorePassRegistry.PassStatus status) = registry.passInfo(handler.ids(i));
            if (status != QorePassRegistry.PassStatus.None) existing++;
        }
        assertEq(uint256(registry.totalIssued()), existing);
    }

    /// @dev Checked-in count equals the passes that carry a check-in time.
    function invariant_checkedInCountMatchesPasses() public view {
        uint256 checked;
        uint256 n = handler.idsLength();
        for (uint256 i = 0; i < n; i++) {
            (,,,,,,, uint64 checkedInAt,) = registry.passInfo(handler.ids(i));
            if (checkedInAt != 0) checked++;
        }
        assertEq(uint256(registry.totalCheckedIn()), checked);
    }

    /// @dev Revoked count equals the passes whose status is Revoked.
    function invariant_revokedCountMatchesPasses() public view {
        uint256 revoked;
        uint256 n = handler.idsLength();
        for (uint256 i = 0; i < n; i++) {
            (,,,,,,, , QorePassRegistry.PassStatus status) = registry.passInfo(handler.ids(i));
            if (status == QorePassRegistry.PassStatus.Revoked) revoked++;
        }
        assertEq(uint256(registry.totalRevoked()), revoked);
    }

    /// @dev The issuer's approval nonce is exactly the authorisations it gave:
    ///      one per issued pass and one per revoked pass, never less.
    function invariant_nonceTracksAuthorisations() public view {
        (,,, uint32 passCount, uint32 nonce,) = registry.issuerInfo(issuer);
        assertEq(uint256(nonce), uint256(passCount) + uint256(handler.ghostRevoked()));
    }

    /// @dev A revoked pass never comes back, and never appears checked in.
    function invariant_revokedIsFinal() public view {
        uint256 n = handler.idsLength();
        for (uint256 i = 0; i < n; i++) {
            bytes32 passId = handler.ids(i);
            if (!handler.everRevoked(passId)) continue;
            (,,,,,,, uint64 checkedInAt, QorePassRegistry.PassStatus status) = registry.passInfo(passId);
            assertEq(uint8(status), uint8(QorePassRegistry.PassStatus.Revoked));
            assertEq(checkedInAt, 0);
            assertEq(registry.passState(passId), 4);
        }
    }

    /// @dev A check-in time, once written, never moves.
    function invariant_checkInTimeIsWriteOnce() public view {
        uint256 n = handler.idsLength();
        for (uint256 i = 0; i < n; i++) {
            bytes32 passId = handler.ids(i);
            uint64 first = handler.firstCheckedInAt(passId);
            if (first == 0) continue;
            (,,,,,, uint64 checkedInAt,,) = registry.passInfo(passId);
            assertEq(checkedInAt, first);
        }
    }

    /// @dev No pass can ever exist without a holder key commitment.
    function invariant_holderKeyAlwaysBound() public view {
        uint256 n = handler.idsLength();
        for (uint256 i = 0; i < n; i++) {
            (,,,, bytes32 holderKeyHash,,,,) = registry.passInfo(handler.ids(i));
            assertTrue(holderKeyHash != bytes32(0));
        }
    }
}
