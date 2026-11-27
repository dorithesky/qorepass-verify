// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {QorePassRegistry} from "../src/QorePassRegistry.sol";
import {MockPQCVerify, MockPQCKeys} from "../src/mocks/MockPQC.sol";

/// @notice The paths the happy-path suite never walks: the constructor's guard,
///         an issuer whose on-chain key changes underneath the registry, a
///         precompile that stops answering, and revocation's own refusals.
contract QorePassEdgeTest is Test {
    QorePassRegistry internal registry;

    address internal constant PQC_VERIFY = 0x0000000000000000000000000000000000000a01;
    address internal constant PQC_KEYS = 0x0000000000000000000000000000000000000a02;

    address internal admin = address(0xA11CE);
    address internal issuer = address(0x1550E);
    address internal secondIssuer = address(0x15502);
    address internal venue = address(0x7E9E);

    bytes internal issuerKey = "issuer-ml-dsa-87-public-key";
    bytes internal secondIssuerKey = "second-issuer-ml-dsa-87-key";
    bytes internal holderKey = "holder-ml-dsa-87-public-key";
    bytes32 internal constant EVENT_ID = keccak256("qorechain-demo-day-2026");
    bytes32 internal constant META_HASH = keccak256('{"tier":"builder"}');
    bytes32 internal constant REASON = keccak256("refunded");

    function setUp() public {
        vm.etch(PQC_VERIFY, address(new MockPQCVerify()).code);
        vm.etch(PQC_KEYS, address(new MockPQCKeys()).code);
        registry = new QorePassRegistry(admin);
        MockPQCKeys(PQC_KEYS).setKey(issuer, 1, issuerKey, true);
        MockPQCKeys(PQC_KEYS).setKey(secondIssuer, 1, secondIssuerKey, true);
        _register(issuer, issuerKey);
        _register(secondIssuer, secondIssuerKey);
    }

    function _sign(bytes memory message) internal pure returns (bytes memory) {
        return abi.encodePacked(bytes1(0x01), message);
    }

    function _register(address who, bytes memory key) internal {
        bytes memory message = registry.registerIssuerMessage(who, keccak256("QoreChain Demo Day"));
        vm.prank(who);
        registry.registerIssuer(key, _sign(message), "QoreChain Demo Day");
    }

    function _issue(address who, bytes32 passId, uint64 validUntil) internal {
        bytes memory message = registry.issuePassMessage(
            who, passId, address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, registry.issuerNonce(who)
        );
        vm.prank(who);
        registry.issuePass(passId, address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, _sign(message));
    }

    // ------------------------------------------------------------------ //
    // constructor
    // ------------------------------------------------------------------ //

    function testConstructorRefusesZeroAdmin() public {
        vm.expectRevert(QorePassRegistry.ZeroAddress.selector);
        new QorePassRegistry(address(0));
    }

    // ------------------------------------------------------------------ //
    // registration
    // ------------------------------------------------------------------ //

    function testRegisterIssuerRefusedWithEmptyKey() public {
        address fresh = address(0xF4E5);
        MockPQCKeys(PQC_KEYS).setKey(fresh, 1, "a-key-registered-for-fresh", true);
        bytes memory message = registry.registerIssuerMessage(fresh, keccak256("name"));
        vm.prank(fresh);
        vm.expectRevert(QorePassRegistry.ZeroHolderKey.selector);
        registry.registerIssuer("", _sign(message), "name");
    }

    function testRegisterIssuerRefusedForAnotherAlgorithm() public {
        address pqc2025 = address(0xC0FFEE);
        MockPQCKeys(PQC_KEYS).setKey(pqc2025, 2, "a-slh-dsa-key", true);
        bytes memory message = registry.registerIssuerMessage(pqc2025, keccak256("name"));
        vm.prank(pqc2025);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.IssuerKeyAlgorithm.selector, uint8(2)));
        registry.registerIssuer("a-slh-dsa-key", _sign(message), "name");
    }

    function testSetIssuerActiveRefusedForUnknownIssuer() public {
        vm.prank(admin);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.IssuerUnknown.selector, venue));
        registry.setIssuerActive(venue, false);
    }

    // ------------------------------------------------------------------ //
    // the chain's key changes under the registry
    // ------------------------------------------------------------------ //

    function testIssueRefusedWhenChainKeyIsGone() public {
        MockPQCKeys(PQC_KEYS).clearKey(issuer);
        uint64 validUntil = uint64(block.timestamp + 1 days);
        bytes memory message = registry.issuePassMessage(
            issuer, bytes32("p1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, 0
        );
        bytes memory signature = _sign(message);
        vm.prank(issuer);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.IssuerKeyNotRegistered.selector, issuer));
        registry.issuePass(bytes32("p1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, signature);
    }

    function testIssueRefusedWhenChainKeyIsRotated() public {
        // the account rotates to a new ML-DSA-87 key after registering here
        MockPQCKeys(PQC_KEYS).setKey(issuer, 1, "a-newly-rotated-key", true);
        uint64 validUntil = uint64(block.timestamp + 1 days);
        bytes memory message = registry.issuePassMessage(
            issuer, bytes32("p1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, 0
        );
        bytes memory signature = _sign(message);
        vm.prank(issuer);
        vm.expectRevert(QorePassRegistry.IssuerKeyMismatch.selector);
        registry.issuePass(bytes32("p1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, signature);
    }

    function testIssueRefusedWhenChainKeyBecomesAnotherAlgorithm() public {
        MockPQCKeys(PQC_KEYS).setKey(issuer, 3, issuerKey, true);
        uint64 validUntil = uint64(block.timestamp + 1 days);
        bytes memory message = registry.issuePassMessage(
            issuer, bytes32("p1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, 0
        );
        bytes memory signature = _sign(message);
        vm.prank(issuer);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.IssuerKeyAlgorithm.selector, uint8(3)));
        registry.issuePass(bytes32("p1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, signature);
    }

    function testIssueRefusedWhenVerifyPrecompileIsGone() public {
        vm.etch(PQC_VERIFY, "");
        uint64 validUntil = uint64(block.timestamp + 1 days);
        bytes memory message = registry.issuePassMessage(
            issuer, bytes32("p1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, 0
        );
        bytes memory signature = _sign(message);
        vm.prank(issuer);
        vm.expectRevert(QorePassRegistry.PrecompileUnavailable.selector);
        registry.issuePass(bytes32("p1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, signature);
    }

    function testCheckInRefusedWhenVerifyPrecompileIsGone() public {
        _issue(issuer, bytes32("p1"), uint64(block.timestamp + 1 days));
        vm.etch(PQC_VERIFY, "");
        bytes memory signature = _sign(registry.checkInMessage(bytes32("p1"), keccak256(holderKey)));
        vm.prank(venue);
        vm.expectRevert(QorePassRegistry.PrecompileUnavailable.selector);
        registry.checkIn(bytes32("p1"), holderKey, signature);
    }

    // ------------------------------------------------------------------ //
    // issuance guards
    // ------------------------------------------------------------------ //

    function testIssueRefusedWithZeroHolderKeyHash() public {
        uint64 validUntil = uint64(block.timestamp + 1 days);
        bytes memory message = registry.issuePassMessage(
            issuer, bytes32("p1"), address(0), EVENT_ID, META_HASH, bytes32(0), validUntil, 0
        );
        bytes memory signature = _sign(message);
        vm.prank(issuer);
        vm.expectRevert(QorePassRegistry.ZeroHolderKey.selector);
        registry.issuePass(bytes32("p1"), address(0), EVENT_ID, META_HASH, bytes32(0), validUntil, signature);
    }

    // ------------------------------------------------------------------ //
    // revocation guards
    // ------------------------------------------------------------------ //

    function testRevokeUnknownPassRefused() public {
        bytes memory signature = _sign(registry.revokePassMessage(issuer, bytes32("nope"), REASON, 0));
        vm.prank(issuer);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.PassUnknown.selector, bytes32("nope")));
        registry.revokePass(bytes32("nope"), REASON, signature);
    }

    function testRevokeOfAnotherIssuersPassRefused() public {
        _issue(issuer, bytes32("p1"), uint64(block.timestamp + 1 days));
        // the second issuer is registered, so this is the "not your pass" path
        bytes memory signature = _sign(
            registry.revokePassMessage(secondIssuer, bytes32("p1"), REASON, registry.issuerNonce(secondIssuer))
        );
        vm.prank(secondIssuer);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.NotAnIssuer.selector, secondIssuer));
        registry.revokePass(bytes32("p1"), REASON, signature);
    }

    function testDoubleRevokeRefused() public {
        _issue(issuer, bytes32("p1"), uint64(block.timestamp + 1 days));
        uint32 nonce = registry.issuerNonce(issuer);
        bytes memory first = _sign(registry.revokePassMessage(issuer, bytes32("p1"), REASON, nonce));
        vm.prank(issuer);
        registry.revokePass(bytes32("p1"), REASON, first);

        bytes memory second = _sign(
            registry.revokePassMessage(issuer, bytes32("p1"), REASON, registry.issuerNonce(issuer))
        );
        vm.prank(issuer);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.PassAlreadyRevoked.selector, bytes32("p1")));
        registry.revokePass(bytes32("p1"), REASON, second);
    }

    function testRevokeRefusedWhenIssuerIsSuspended() public {
        _issue(issuer, bytes32("p1"), uint64(block.timestamp + 1 days));
        vm.prank(admin);
        registry.setIssuerActive(issuer, false);
        bytes memory signature = _sign(registry.revokePassMessage(issuer, bytes32("p1"), REASON, 1));
        vm.prank(issuer);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.NotAnIssuer.selector, issuer));
        registry.revokePass(bytes32("p1"), REASON, signature);
    }

    function testRevokeRefusedWithForgedSignature() public {
        _issue(issuer, bytes32("p1"), uint64(block.timestamp + 1 days));
        vm.prank(issuer);
        vm.expectRevert(QorePassRegistry.BadIssuerSignature.selector);
        registry.revokePass(bytes32("p1"), REASON, _sign("not the message"));
    }

    function testRevokeRefusedWhenVerifyPrecompileIsGone() public {
        _issue(issuer, bytes32("p1"), uint64(block.timestamp + 1 days));
        bytes memory signature = _sign(registry.revokePassMessage(issuer, bytes32("p1"), REASON, 1));
        vm.etch(PQC_VERIFY, "");
        vm.prank(issuer);
        vm.expectRevert(QorePassRegistry.PrecompileUnavailable.selector);
        registry.revokePass(bytes32("p1"), REASON, signature);
    }

    // ------------------------------------------------------------------ //
    // views
    // ------------------------------------------------------------------ //

    function testPassStatesAcrossTheLifecycle() public {
        uint64 validUntil = uint64(block.timestamp + 1 days);
        _issue(issuer, bytes32("p1"), validUntil);
        assertEq(registry.passState(bytes32("p1")), 1);
        assertTrue(registry.isValid(bytes32("p1")));

        bytes memory signature = _sign(registry.checkInMessage(bytes32("p1"), keccak256(holderKey)));
        vm.prank(venue);
        registry.checkIn(bytes32("p1"), holderKey, signature);
        assertEq(registry.passState(bytes32("p1")), 2);
        assertFalse(registry.isValid(bytes32("p1")));

        // and a pass that was never checked in expires on its own
        _issue(issuer, bytes32("p2"), uint64(block.timestamp + 1 hours));
        vm.warp(block.timestamp + 2 hours);
        assertEq(registry.passState(bytes32("p2")), 3);
    }

    function testCheckedInPassCanStillBeRevoked() public {
        // a refund after the holder attended: the record keeps both facts
        _issue(issuer, bytes32("p1"), uint64(block.timestamp + 1 days));
        bytes memory checkInSig = _sign(registry.checkInMessage(bytes32("p1"), keccak256(holderKey)));
        vm.prank(venue);
        registry.checkIn(bytes32("p1"), holderKey, checkInSig);

        uint32 nonce = registry.issuerNonce(issuer);
        bytes memory revokeSig = _sign(registry.revokePassMessage(issuer, bytes32("p1"), REASON, nonce));
        vm.prank(issuer);
        registry.revokePass(bytes32("p1"), REASON, revokeSig);

        assertEq(registry.passState(bytes32("p1")), 4);
        assertEq(registry.totalCheckedIn(), 1);
        assertEq(registry.totalRevoked(), 1);
    }
}
