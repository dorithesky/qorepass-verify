// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {QorePassRegistry} from "../src/QorePassRegistry.sol";
import {MockPQCVerify, MockPQCKeys} from "../src/mocks/MockPQC.sol";

/// @notice Behavioural tests for the pass lifecycle. The two QoreChain
///         precompiles are etched as mocks, and a "signature" is `0x01 || msg`
///         so signing is a pure function of the message — the same property
///         ML-DSA-87 gives us on the real chain.
contract QorePassRegistryTest is Test {
    event PassIssued(
        bytes32 indexed passId,
        address indexed issuer,
        address indexed holder,
        bytes32 eventId,
        bytes32 holderKeyHash,
        uint64 validUntil,
        uint32 approvalNonce,
        bytes32 metaHash
    );

    QorePassRegistry internal registry;

    address internal constant PQC_VERIFY = 0x0000000000000000000000000000000000000a01;
    address internal constant PQC_KEYS = 0x0000000000000000000000000000000000000a02;

    address internal admin = address(0xA11CE);
    address internal issuer = address(0x1550E);
    address internal venue = address(0x7E9E);
    address internal outsider = address(0xBAD);

    bytes internal issuerKey = "issuer-ml-dsa-87-public-key";
    bytes internal holderKey = "holder-ml-dsa-87-public-key";
    bytes internal otherHolderKey = "someone-elses-ml-dsa-87-key";

    bytes32 internal constant EVENT_ID = keccak256("qorechain-demo-day-2026");
    bytes32 internal constant META_HASH = keccak256('{"tier":"builder","seat":"A-12"}');
    bytes32 internal constant REASON = keccak256("refunded");

    function setUp() public {
        // etch the precompiles
        vm.etch(PQC_VERIFY, address(new MockPQCVerify()).code);
        vm.etch(PQC_KEYS, address(new MockPQCKeys()).code);

        registry = new QorePassRegistry(admin);

        // the chain knows issuer's post-quantum key
        MockPQCKeys(PQC_KEYS).setKey(issuer, 1, issuerKey, true);
    }

    // ------------------------------------------------------------------ //
    // Helpers
    // ------------------------------------------------------------------ //

    function sign(bytes memory message) internal pure returns (bytes memory) {
        return abi.encodePacked(bytes1(0x01), message);
    }

    function registerIssuer(address who) internal {
        bytes memory message = registry.registerIssuerMessage(who, keccak256("QoreChain Demo Day"));
        vm.prank(who);
        registry.registerIssuer(issuerKey, sign(message), "QoreChain Demo Day");
    }

    function issue(bytes32 passId, uint64 validUntil) internal {
        uint32 nonce = registry.issuerNonce(issuer);
        bytes memory message = registry.issuePassMessage(
            issuer, passId, address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, nonce
        );
        vm.prank(issuer);
        registry.issuePass(passId, address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, sign(message));
    }

    function checkIn(bytes32 passId, bytes memory pubkey) internal {
        bytes memory message = registry.checkInMessage(passId, keccak256(holderKey));
        bytes memory signature = sign(message);
        vm.prank(venue);
        registry.checkIn(passId, pubkey, signature);
    }

    /// @dev Hoists every view call out of the prank/expectRevert window: a
    ///      pranked or expected call is consumed by the very next external call,
    ///      including a `view` helper on the registry.
    function checkInExpectingRevert(bytes32 passId, bytes memory pubkey, bytes memory message, bytes4 selector)
        internal
    {
        bytes memory signature = sign(message);
        vm.prank(venue);
        vm.expectRevert(selector);
        registry.checkIn(passId, pubkey, signature);
    }

    // ------------------------------------------------------------------ //
    // Issuers
    // ------------------------------------------------------------------ //

    function testRegisterIssuerBindsChainKey() public {
        registerIssuer(issuer);

        (bytes32 pubkeyHash, bytes32 nameHash,, uint32 passCount, uint32 nonce, bool active) =
            registry.issuerInfo(issuer);
        assertEq(pubkeyHash, keccak256(issuerKey));
        assertEq(nameHash, keccak256("QoreChain Demo Day"));
        assertEq(passCount, 0);
        assertEq(nonce, 0);
        assertTrue(active);
    }

    function testRegisterIssuerRefusedWithoutChainKey() public {
        bytes memory message = registry.registerIssuerMessage(outsider, keccak256("Nobody"));
        vm.prank(outsider);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.IssuerKeyNotRegistered.selector, outsider));
        registry.registerIssuer(issuerKey, sign(message), "Nobody");
    }

    function testRegisterIssuerRefusedWhenKeyDiffersFromChainKey() public {
        bytes memory message = registry.registerIssuerMessage(issuer, keccak256("Impostor"));
        vm.prank(issuer);
        vm.expectRevert(QorePassRegistry.IssuerKeyMismatch.selector);
        registry.registerIssuer("a-key-the-chain-does-not-hold", sign(message), "Impostor");
    }

    function testRegisterIssuerRefusedWithBadSignature() public {
        bytes memory message = registry.registerIssuerMessage(issuer, keccak256("QoreChain Demo Day"));
        vm.prank(issuer);
        vm.expectRevert(QorePassRegistry.BadIssuerSignature.selector);
        registry.registerIssuer(issuerKey, sign("some other message"), "QoreChain Demo Day");
    }

    function testRegisterIssuerTwiceRefused() public {
        registerIssuer(issuer);
        bytes memory message = registry.registerIssuerMessage(issuer, keccak256("Second Name"));
        vm.prank(issuer);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.IssuerExists.selector, issuer));
        registry.registerIssuer(issuerKey, sign(message), "Second Name");
    }

    function testAdminCanSuspendAndRestoreIssuer() public {
        registerIssuer(issuer);
        vm.prank(admin);
        registry.setIssuerActive(issuer, false);
        assertFalse(issuerActive(issuer));

        uint64 validUntil = uint64(block.timestamp + 1 days);
        bytes memory message = registry.issuePassMessage(
            issuer, bytes32("p1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, 0
        );
        bytes memory signature = sign(message);
        vm.prank(issuer);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.NotAnIssuer.selector, issuer));
        registry.issuePass(bytes32("p1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, signature);

        vm.prank(admin);
        registry.setIssuerActive(issuer, true);
        assertTrue(issuerActive(issuer));
    }

    function testOnlyAdminCanSuspend() public {
        registerIssuer(issuer);
        vm.prank(outsider);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.NotAdmin.selector, outsider));
        registry.setIssuerActive(issuer, false);
    }

    function issuerPassCount(address who) internal view returns (uint32) {
        (,,, uint32 passCount,,) = registry.issuerInfo(who);
        return passCount;
    }

    function issuerActive(address who) internal view returns (bool) {
        (,,,,, bool active) = registry.issuerInfo(who);
        return active;
    }

    // ------------------------------------------------------------------ //
    // Issuing
    // ------------------------------------------------------------------ //

    function testIssuePassStoresEverything() public {
        registerIssuer(issuer);
        uint64 validUntil = uint64(block.timestamp + 2 days);
        issue(bytes32("pass-1"), validUntil);

        (
            address passIssuer,
            address holder,
            bytes32 eventId,
            bytes32 metaHash,
            bytes32 holderKeyHash,
            uint64 storedValidUntil,
            uint64 issuedAt,
            uint64 checkedInAt,
            QorePassRegistry.PassStatus status
        ) = registry.passInfo(bytes32("pass-1"));

        assertEq(passIssuer, issuer);
        assertEq(holder, address(0));
        assertEq(eventId, EVENT_ID);
        assertEq(metaHash, META_HASH);
        assertEq(holderKeyHash, keccak256(holderKey));
        assertEq(storedValidUntil, validUntil);
        assertEq(issuedAt, block.timestamp);
        assertEq(checkedInAt, 0);
        assertEq(uint8(status), uint8(QorePassRegistry.PassStatus.Active));
        assertEq(registry.totalIssued(), 1);
        assertEq(registry.passState(bytes32("pass-1")), 1);
    }

    function testIssueAdvancesIssuerNonce() public {
        registerIssuer(issuer);
        issue(bytes32("pass-1"), uint64(block.timestamp + 1 days));
        issue(bytes32("pass-2"), uint64(block.timestamp + 1 days));
        assertEq(registry.issuerNonce(issuer), 2);
        assertEq(issuerPassCount(issuer), 2);
    }

    function testReplayedIssueSignatureRefused() public {
        registerIssuer(issuer);
        uint64 validUntil = uint64(block.timestamp + 1 days);
        bytes memory message = registry.issuePassMessage(
            issuer, bytes32("pass-1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, 0
        );
        vm.prank(issuer);
        registry.issuePass(bytes32("pass-1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, sign(message));

        // the same signature for a second pass id, and the nonce it was made at
        vm.prank(issuer);
        vm.expectRevert(QorePassRegistry.BadIssuerSignature.selector);
        registry.issuePass(bytes32("pass-2"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, sign(message));
    }

    function testIssueRefusedForUnregisteredIssuer() public {
        bytes memory message = registry.issuePassMessage(
            outsider, bytes32("pass-1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), uint64(block.timestamp + 1 days), 0
        );
        vm.prank(outsider);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.NotAnIssuer.selector, outsider));
        registry.issuePass(
            bytes32("pass-1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), uint64(block.timestamp + 1 days), sign(message)
        );
    }

    function testIssueRefusedForDuplicatePassId() public {
        registerIssuer(issuer);
        issue(bytes32("pass-1"), uint64(block.timestamp + 1 days));
        bytes memory message = registry.issuePassMessage(
            issuer, bytes32("pass-1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), uint64(block.timestamp + 1 days), 1
        );
        vm.prank(issuer);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.PassExists.selector, bytes32("pass-1")));
        registry.issuePass(
            bytes32("pass-1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), uint64(block.timestamp + 1 days), sign(message)
        );
    }

    function testIssueRefusedWhenAlreadyExpired() public {
        registerIssuer(issuer);
        uint64 validUntil = uint64(block.timestamp - 1);
        bytes memory message = registry.issuePassMessage(
            issuer, bytes32("pass-1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, 0
        );
        vm.prank(issuer);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.ValidityTooShort.selector, validUntil));
        registry.issuePass(bytes32("pass-1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, sign(message));
    }

    function testIssueRefusedBeyondMaximumValidity() public {
        registerIssuer(issuer);
        uint64 validUntil = uint64(block.timestamp + 3651 days);
        bytes memory message = registry.issuePassMessage(
            issuer, bytes32("pass-1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, 0
        );
        vm.prank(issuer);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.ValidityTooLong.selector, validUntil));
        registry.issuePass(bytes32("pass-1"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, sign(message));
    }

    /// @dev The Q-Day case: an attacker who has the issuer's classical ECDSA
    ///      key (and therefore the account) but not its ML-DSA-87 key cannot
    ///      mint a pass.
    function testIssuerWithStolenClassicalKeyCannotMint() public {
        registerIssuer(issuer);
        uint64 validUntil = uint64(block.timestamp + 1 days);
        bytes memory message = registry.issuePassMessage(
            issuer, bytes32("forged"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, 0
        );
        // a signature over the right message with a key that is not the issuer's
        bytes memory forged = sign("attacker signature");
        vm.prank(issuer);
        vm.expectRevert(QorePassRegistry.BadIssuerSignature.selector);
        registry.issuePass(bytes32("forged"), address(0), EVENT_ID, META_HASH, keccak256(holderKey), validUntil, forged);
    }

    // ------------------------------------------------------------------ //
    // Check-in
    // ------------------------------------------------------------------ //

    function testCheckInWithHolderKey() public {
        registerIssuer(issuer);
        issue(bytes32("pass-1"), uint64(block.timestamp + 1 days));

        checkIn(bytes32("pass-1"), holderKey);

        (,,,,, uint64 validUntil, uint64 issuedAt, uint64 checkedInAt,) = registry.passInfo(bytes32("pass-1"));
        assertEq(checkedInAt, block.timestamp);
        assertEq(registry.passState(bytes32("pass-1")), 2); // checked in
        assertEq(issuedAt, checkedInAt);
        assertLe(checkedInAt, validUntil);
        assertEq(registry.totalCheckedIn(), 1);
    }

    function testCheckInRefusedWithoutHolderKey() public {
        registerIssuer(issuer);
        issue(bytes32("pass-1"), uint64(block.timestamp + 1 days));
        checkInExpectingRevert(
            bytes32("pass-1"),
            otherHolderKey,
            registry.checkInMessage(bytes32("pass-1"), keccak256(holderKey)),
            QorePassRegistry.HolderKeyMismatch.selector
        );
    }

    function testCheckInRefusedWithWrongSignature() public {
        registerIssuer(issuer);
        issue(bytes32("pass-1"), uint64(block.timestamp + 1 days));
        bytes memory signature = sign("signed something else");
        vm.prank(venue);
        vm.expectRevert(QorePassRegistry.BadHolderSignature.selector);
        registry.checkIn(bytes32("pass-1"), holderKey, signature);
    }

    function testDoubleCheckInRefused() public {
        registerIssuer(issuer);
        issue(bytes32("pass-1"), uint64(block.timestamp + 1 days));
        checkIn(bytes32("pass-1"), holderKey);

        bytes memory signature = sign(registry.checkInMessage(bytes32("pass-1"), keccak256(holderKey)));
        vm.prank(venue);
        vm.expectRevert(
            abi.encodeWithSelector(QorePassRegistry.AlreadyCheckedIn.selector, bytes32("pass-1"), uint64(block.timestamp))
        );
        registry.checkIn(bytes32("pass-1"), holderKey, signature);
    }

    function testCheckInRefusedAfterExpiry() public {
        registerIssuer(issuer);
        uint64 validUntil = uint64(block.timestamp + 1 hours);
        issue(bytes32("pass-1"), validUntil);
        vm.warp(validUntil + 1);

        bytes memory signature = sign(registry.checkInMessage(bytes32("pass-1"), keccak256(holderKey)));
        vm.prank(venue);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.PassExpired.selector, bytes32("pass-1"), validUntil));
        registry.checkIn(bytes32("pass-1"), holderKey, signature);
        assertEq(registry.passState(bytes32("pass-1")), 3); // expired
    }

    function testCheckInRefusedForUnknownPass() public {
        bytes memory signature = sign("anything");
        vm.prank(venue);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.PassUnknown.selector, bytes32("nope")));
        registry.checkIn(bytes32("nope"), holderKey, signature);
    }

    // ------------------------------------------------------------------ //
    // Revocation
    // ------------------------------------------------------------------ //

    function testRevokePass() public {
        registerIssuer(issuer);
        issue(bytes32("pass-1"), uint64(block.timestamp + 1 days));

        uint32 nonce = registry.issuerNonce(issuer);
        bytes memory signature = sign(registry.revokePassMessage(issuer, bytes32("pass-1"), REASON, nonce));
        vm.prank(issuer);
        registry.revokePass(bytes32("pass-1"), REASON, signature);

        assertEq(registry.passState(bytes32("pass-1")), 4); // revoked
        assertEq(registry.totalRevoked(), 1);
        assertFalse(registry.isValid(bytes32("pass-1")));
    }

    function testCheckInRefusedAfterRevocation() public {
        registerIssuer(issuer);
        issue(bytes32("pass-1"), uint64(block.timestamp + 1 days));
        uint32 nonce = registry.issuerNonce(issuer);
        bytes memory revokeSig = sign(registry.revokePassMessage(issuer, bytes32("pass-1"), REASON, nonce));
        vm.prank(issuer);
        registry.revokePass(bytes32("pass-1"), REASON, revokeSig);

        bytes memory checkInSig = sign(registry.checkInMessage(bytes32("pass-1"), keccak256(holderKey)));
        vm.prank(venue);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.PassAlreadyRevoked.selector, bytes32("pass-1")));
        registry.checkIn(bytes32("pass-1"), holderKey, checkInSig);
    }

    function testOnlyIssuingAccountCanRevoke() public {
        registerIssuer(issuer);
        issue(bytes32("pass-1"), uint64(block.timestamp + 1 days));
        uint32 nonce = registry.issuerNonce(issuer);
        bytes memory signature = sign(registry.revokePassMessage(outsider, bytes32("pass-1"), REASON, nonce));
        vm.prank(outsider);
        vm.expectRevert(abi.encodeWithSelector(QorePassRegistry.NotAnIssuer.selector, outsider));
        registry.revokePass(bytes32("pass-1"), REASON, signature);
    }

    function testRevokeRefusedWithReplayedSignature() public {
        registerIssuer(issuer);
        issue(bytes32("pass-1"), uint64(block.timestamp + 1 days));
        issue(bytes32("pass-2"), uint64(block.timestamp + 1 days));

        uint32 nonce = registry.issuerNonce(issuer);
        bytes memory signature = sign(registry.revokePassMessage(issuer, bytes32("pass-1"), REASON, nonce));
        vm.prank(issuer);
        registry.revokePass(bytes32("pass-1"), REASON, signature);

        vm.prank(issuer);
        vm.expectRevert(QorePassRegistry.BadIssuerSignature.selector);
        registry.revokePass(bytes32("pass-2"), REASON, signature);
    }

    // ------------------------------------------------------------------ //
    // Message binding
    // ------------------------------------------------------------------ //

    function testMessagesBindChainContractAndAction() public {
        bytes32 passId = bytes32("pass-1");
        bytes memory m1 = registry.issuePassMessage(issuer, passId, address(0), EVENT_ID, META_HASH, keccak256(holderKey), 1000, 0);
        bytes memory m2 = registry.issuePassMessage(issuer, passId, address(0), EVENT_ID, META_HASH, keccak256(holderKey), 1001, 0);
        assertTrue(keccak256(m1) != keccak256(m2));

        assertTrue(keccak256(registry.checkInMessage(passId, keccak256(holderKey))) != keccak256(m1));
        assertTrue(keccak256(m1) != keccak256(registry.issuePassMessage(outsider, passId, address(0), EVENT_ID, META_HASH, keccak256(holderKey), 1000, 0)));
    }

    function testPrecompileUnavailableNeverReadsAsRegistered() public {
        // an address with no code answers empty data
        vm.etch(PQC_KEYS, "");
        bytes memory message = registry.registerIssuerMessage(issuer, keccak256("QoreChain Demo Day"));
        vm.prank(issuer);
        vm.expectRevert(QorePassRegistry.PrecompileUnavailable.selector);
        registry.registerIssuer(issuerKey, sign(message), "QoreChain Demo Day");
    }

    function testPassStateForUnknownPass() public view {
        assertEq(registry.passState(bytes32("never-issued")), 0);
    }
}
