// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

/// @title QorePass — a post-quantum pass registry
/// @notice Issues, checks in and revokes passes (event badges, credentials,
///         receipts) where every state change is authorised by an
///         **ML-DSA-87 (FIPS 204)** signature verified on chain by QoreChain's
///         `pqcVerify` precompile. A pass belongs to a *post-quantum key*, not
///         to a wallet: a screenshot of the pass, a copied pass id, or even the
///         holder's classical key cannot check it in.
///
///         Three authorisation rules, all enforced here:
///         1. Only an issuer registered with its own ML-DSA-87 key may create
///            or revoke a pass, and every issue/revoke carries a fresh
///            signature over a message bound to this chain and this contract
///            with a monotonic per-issuer nonce.
///         2. A pass carries `keccak256(holderPubkey)` at issuance. Check-in
///            requires the holder's ML-DSA-87 key and a signature over the
///            check-in message, so possession of the pass id is not enough.
///         3. The issuer's key is the key registered for its own QoreChain
///            account (`pqcKeyStatus`), so an issuer cannot sign with a key
///            the chain does not know it owns.
///
///         Nothing here can be replayed on another chain or another contract:
///         every message starts with the domain, `block.chainid` and
///         `address(this)`.
contract QorePassRegistry {
    // ------------------------------------------------------------------ //
    // Chain constants
    // ------------------------------------------------------------------ //

    /// @dev `pqcVerify(bytes pubkey, bytes signature, bytes message) -> bool`
    address public constant PQC_VERIFY = 0x0000000000000000000000000000000000000a01;
    /// @dev `pqcKeyStatus(address) -> (bool,uint8,bytes,bool)`
    address public constant PQC_KEYS = 0x0000000000000000000000000000000000000a02;

    /// @dev Algorithm id 1 = ML-DSA-87 (Dilithium-5).
    uint8 public constant ML_DSA_87 = 1;

    bytes public constant DOMAIN = "QOREPASS:v1";

    bytes32 public constant A_REGISTER_ISSUER = keccak256("registerIssuer");
    bytes32 public constant A_ISSUE_PASS = keccak256("issuePass");
    bytes32 public constant A_CHECK_IN = keccak256("checkIn");
    bytes32 public constant A_REVOKE_PASS = keccak256("revokePass");

    /// @dev No pass may claim to be valid for more than ten years.
    uint64 public constant MAX_VALIDITY = 3650 days;

    enum PassStatus {
        None,
        Active,
        Revoked
    }

    struct Issuer {
        bytes32 pubkeyHash; // keccak256(ML-DSA-87 public key)
        bytes32 nameHash; // keccak256(UTF-8 name)
        uint64 registeredAt;
        uint32 passCount;
        uint32 approvalNonce; // monotonic, one per issue/revoke
        bool active;
    }

    struct Pass {
        address issuer;
        address holder; // optional account binding; address(0) is allowed
        bytes32 eventId;
        bytes32 metaHash; // commitment to the off-chain pass metadata
        bytes32 holderKeyHash; // keccak256(holder ML-DSA-87 public key)
        uint64 validUntil;
        uint64 issuedAt;
        uint64 checkedInAt;
        PassStatus status;
    }

    // ------------------------------------------------------------------ //
    // State
    // ------------------------------------------------------------------ //

    address public immutable admin;

    mapping(address => Issuer) public issuers;
    mapping(bytes32 => Pass) internal _passes;

    uint32 public totalIssued;
    uint32 public totalCheckedIn;
    uint32 public totalRevoked;

    // ------------------------------------------------------------------ //
    // Events
    // ------------------------------------------------------------------ //

    event IssuerRegistered(address indexed issuer, bytes32 pubkeyHash, bytes32 nameHash, bool possessionProven);
    event IssuerStatusChanged(address indexed issuer, bool active);
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
    event PassCheckedIn(bytes32 indexed passId, address indexed issuer, bytes32 holderKeyHash, uint64 checkedInAt);
    event PassRevoked(bytes32 indexed passId, address indexed issuer, bytes32 reasonHash, uint32 approvalNonce);

    // ------------------------------------------------------------------ //
    // Errors
    // ------------------------------------------------------------------ //

    error NotAdmin(address caller);
    error NotAnIssuer(address caller);
    error IssuerExists(address issuer);
    error IssuerUnknown(address issuer);
    error IssuerKeyNotRegistered(address issuer);
    error IssuerKeyAlgorithm(uint8 algorithmId);
    error IssuerKeyMismatch();
    error BadIssuerSignature();
    error BadHolderSignature();
    error PassExists(bytes32 passId);
    error PassUnknown(bytes32 passId);
    error PassAlreadyRevoked(bytes32 passId);
    error PassExpired(bytes32 passId, uint64 validUntil);
    error PassNotExpiredYet(bytes32 passId, uint64 validUntil);
    error AlreadyCheckedIn(bytes32 passId, uint64 checkedInAt);
    error HolderKeyMismatch();
    error ZeroHolderKey();
    error ValidityTooShort(uint64 validUntil);
    error ValidityTooLong(uint64 validUntil);
    error PrecompileUnavailable();
    error ZeroAddress();

    modifier onlyAdmin() {
        if (msg.sender != admin) revert NotAdmin(msg.sender);
        _;
    }

    constructor(address admin_) {
        if (admin_ == address(0)) revert ZeroAddress();
        admin = admin_;
    }

    // ------------------------------------------------------------------ //
    // Messages the issuer / holder sign
    // ------------------------------------------------------------------ //
    // `packed` (not `encode`) on purpose: it is unambiguous here because every
    // field is fixed-width except DOMAIN, and DOMAIN is a compile-time
    // constant. The off-chain signer mirrors these byte for byte, and
    // `scripts/verify_encoding.py` checks the mirror against `eth_call`.

    function registerIssuerMessage(address issuer, bytes32 nameHash) public view returns (bytes memory) {
        return abi.encodePacked(DOMAIN, block.chainid, address(this), A_REGISTER_ISSUER, issuer, nameHash);
    }

    function issuePassMessage(
        address issuer,
        bytes32 passId,
        address holder,
        bytes32 eventId,
        bytes32 metaHash,
        bytes32 holderKeyHash,
        uint64 validUntil,
        uint32 approvalNonce
    ) public view returns (bytes memory) {
        return abi.encodePacked(
            DOMAIN,
            block.chainid,
            address(this),
            A_ISSUE_PASS,
            issuer,
            passId,
            holder,
            eventId,
            metaHash,
            holderKeyHash,
            validUntil,
            approvalNonce
        );
    }

    function checkInMessage(bytes32 passId, bytes32 holderKeyHash) public view returns (bytes memory) {
        return abi.encodePacked(DOMAIN, block.chainid, address(this), A_CHECK_IN, passId, holderKeyHash);
    }

    function revokePassMessage(address issuer, bytes32 passId, bytes32 reasonHash, uint32 approvalNonce)
        public
        view
        returns (bytes memory)
    {
        return abi.encodePacked(
            DOMAIN, block.chainid, address(this), A_REVOKE_PASS, issuer, passId, reasonHash, approvalNonce
        );
    }

    // ------------------------------------------------------------------ //
    // Issuers
    // ------------------------------------------------------------------ //

    /// @notice Self-registration: the caller proves it holds the ML-DSA-87 key
    ///         that its QoreChain account has registered, and binds it to an
    ///         issuer name. No admin transaction is needed to onboard an
    ///         issuer, and the admin can still switch one off.
    function registerIssuer(bytes calldata pqcPubkey, bytes calldata pqcSignature, string calldata name)
        external
    {
        if (issuers[msg.sender].registeredAt != 0) revert IssuerExists(msg.sender);
        if (pqcPubkey.length == 0) revert ZeroHolderKey();

        (bool registered, uint8 algorithmId, bytes memory accountKey, bool proven) = _pqcKeyStatus(msg.sender);
        if (!registered || accountKey.length == 0) revert IssuerKeyNotRegistered(msg.sender);
        if (algorithmId != ML_DSA_87) revert IssuerKeyAlgorithm(algorithmId);
        if (keccak256(accountKey) != keccak256(pqcPubkey)) revert IssuerKeyMismatch();

        bytes32 nameHash = keccak256(bytes(name));
        if (!_pqcVerify(pqcPubkey, pqcSignature, registerIssuerMessage(msg.sender, nameHash))) {
            revert BadIssuerSignature();
        }

        issuers[msg.sender] = Issuer({
            pubkeyHash: keccak256(pqcPubkey),
            nameHash: nameHash,
            registeredAt: uint64(block.timestamp),
            passCount: 0,
            approvalNonce: 0,
            active: true
        });
        emit IssuerRegistered(msg.sender, keccak256(pqcPubkey), nameHash, proven);
    }

    function setIssuerActive(address issuer, bool active) external onlyAdmin {
        if (issuers[issuer].registeredAt == 0) revert IssuerUnknown(issuer);
        issuers[issuer].active = active;
        emit IssuerStatusChanged(issuer, active);
    }

    // ------------------------------------------------------------------ //
    // Passes
    // ------------------------------------------------------------------ //

    /// @notice Issue a pass. The issuer signs the pass exactly once; anyone can
    ///         submit the transaction (the issuer pays gas by submitting it
    ///         itself here, but the signature is what authorises it).
    function issuePass(
        bytes32 passId,
        address holder,
        bytes32 eventId,
        bytes32 metaHash,
        bytes32 holderKeyHash,
        uint64 validUntil,
        bytes calldata pqcSignature
    ) external {
        Issuer storage issuer = issuers[msg.sender];
        if (issuer.registeredAt == 0 || !issuer.active) revert NotAnIssuer(msg.sender);
        if (_passes[passId].status != PassStatus.None) revert PassExists(passId);
        if (holderKeyHash == bytes32(0)) revert ZeroHolderKey();
        if (validUntil <= block.timestamp) revert ValidityTooShort(validUntil);
        if (validUntil > block.timestamp + MAX_VALIDITY) revert ValidityTooLong(validUntil);

        uint32 nonce = issuer.approvalNonce;
        bytes memory message =
            issuePassMessage(msg.sender, passId, holder, eventId, metaHash, holderKeyHash, validUntil, nonce);
        if (!_pqcVerifyForAccount(msg.sender, pqcSignature, message, issuer.pubkeyHash)) {
            revert BadIssuerSignature();
        }

        issuer.approvalNonce = nonce + 1;
        issuer.passCount += 1;
        totalIssued += 1;

        _passes[passId] = Pass({
            issuer: msg.sender,
            holder: holder,
            eventId: eventId,
            metaHash: metaHash,
            holderKeyHash: holderKeyHash,
            validUntil: validUntil,
            issuedAt: uint64(block.timestamp),
            checkedInAt: 0,
            status: PassStatus.Active
        });

        emit PassIssued(passId, msg.sender, holder, eventId, holderKeyHash, validUntil, nonce, metaHash);
    }

    /// @notice Check a pass in. The holder's ML-DSA-87 signature is verified
    ///         against the key hash committed at issuance, so the presenter
    ///         must actually hold the post-quantum key the pass was issued to.
    /// @dev    Submitted by whoever scans (venue, organiser, relayer); the
    ///         signature is the authorisation, not `msg.sender`.
    function checkIn(bytes32 passId, bytes calldata holderPubkey, bytes calldata holderSignature) external {
        Pass storage pass = _passes[passId];
        if (pass.status == PassStatus.None) revert PassUnknown(passId);
        if (pass.status == PassStatus.Revoked) revert PassAlreadyRevoked(passId);
        if (pass.checkedInAt != 0) revert AlreadyCheckedIn(passId, pass.checkedInAt);
        if (block.timestamp > pass.validUntil) revert PassExpired(passId, pass.validUntil);
        if (keccak256(holderPubkey) != pass.holderKeyHash) revert HolderKeyMismatch();
        if (!_pqcVerify(holderPubkey, holderSignature, checkInMessage(passId, pass.holderKeyHash))) {
            revert BadHolderSignature();
        }

        pass.checkedInAt = uint64(block.timestamp);
        totalCheckedIn += 1;
        emit PassCheckedIn(passId, pass.issuer, pass.holderKeyHash, pass.checkedInAt);
    }

    /// @notice Revoke a pass (refund, fraud, lost key). Only the issuing
    ///         account, with a fresh ML-DSA-87 signature and nonce.
    function revokePass(bytes32 passId, bytes32 reasonHash, bytes calldata pqcSignature) external {
        Issuer storage issuer = issuers[msg.sender];
        if (issuer.registeredAt == 0 || !issuer.active) revert NotAnIssuer(msg.sender);
        Pass storage pass = _passes[passId];
        if (pass.status == PassStatus.None) revert PassUnknown(passId);
        if (pass.issuer != msg.sender) revert NotAnIssuer(msg.sender);
        if (pass.status == PassStatus.Revoked) revert PassAlreadyRevoked(passId);

        uint32 nonce = issuer.approvalNonce;
        bytes memory message = revokePassMessage(msg.sender, passId, reasonHash, nonce);
        if (!_pqcVerifyForAccount(msg.sender, pqcSignature, message, issuer.pubkeyHash)) {
            revert BadIssuerSignature();
        }

        issuer.approvalNonce = nonce + 1;
        totalRevoked += 1;
        pass.status = PassStatus.Revoked;
        emit PassRevoked(passId, msg.sender, reasonHash, nonce);
    }

    // ------------------------------------------------------------------ //
    // Views
    // ------------------------------------------------------------------ //

    function passInfo(bytes32 passId)
        external
        view
        returns (
            address issuer,
            address holder,
            bytes32 eventId,
            bytes32 metaHash,
            bytes32 holderKeyHash,
            uint64 validUntil,
            uint64 issuedAt,
            uint64 checkedInAt,
            PassStatus status
        )
    {
        Pass storage p = _passes[passId];
        return (
            p.issuer, p.holder, p.eventId, p.metaHash, p.holderKeyHash, p.validUntil, p.issuedAt, p.checkedInAt, p.status
        );
    }

    /// @notice Machine-readable state for a verifier UI:
    ///         0 = unknown, 1 = valid, 2 = checked in, 3 = expired, 4 = revoked.
    function passState(bytes32 passId) public view returns (uint8) {
        Pass storage p = _passes[passId];
        if (p.status == PassStatus.None) return 0;
        if (p.status == PassStatus.Revoked) return 4;
        if (p.checkedInAt != 0) return 2;
        if (block.timestamp > p.validUntil) return 3;
        return 1;
    }

    function isValid(bytes32 passId) external view returns (bool) {
        return passState(passId) == 1;
    }

    function issuerInfo(address issuer)
        external
        view
        returns (bytes32 pubkeyHash, bytes32 nameHash, uint64 registeredAt, uint32 passCount, uint32 approvalNonce, bool active)
    {
        Issuer storage i = issuers[issuer];
        return (i.pubkeyHash, i.nameHash, i.registeredAt, i.passCount, i.approvalNonce, i.active);
    }

    function issuerNonce(address issuer) external view returns (uint32) {
        return issuers[issuer].approvalNonce;
    }

    // ------------------------------------------------------------------ //
    // Precompile plumbing
    // ------------------------------------------------------------------ //

    /// @dev `pqcKeyStatus` returns empty data when the precompile is not
    ///      active; empty must never be read as "registered".
    function _pqcKeyStatus(address account)
        internal
        view
        returns (bool registered, uint8 algorithmId, bytes memory pubkey, bool proven)
    {
        (bool ok, bytes memory ret) = PQC_KEYS.staticcall(abi.encodeWithSignature("pqcKeyStatus(address)", account));
        if (!ok || ret.length < 128) revert PrecompileUnavailable();
        return abi.decode(ret, (bool, uint8, bytes, bool));
    }

    function _pqcVerify(bytes memory pubkey, bytes memory signature, bytes memory message)
        internal
        view
        returns (bool)
    {
        (bool ok, bytes memory ret) =
            PQC_VERIFY.staticcall(abi.encodeWithSignature("pqcVerify(bytes,bytes,bytes)", pubkey, signature, message));
        if (!ok || ret.length < 32) revert PrecompileUnavailable();
        return abi.decode(ret, (bool));
    }

    /// @dev Verify with the key the chain holds for `account`, after checking
    ///      it is still the key this issuer registered with.
    function _pqcVerifyForAccount(
        address account,
        bytes memory signature,
        bytes memory message,
        bytes32 expectedPubkeyHash
    ) internal view returns (bool) {
        (bool registered, uint8 algorithmId, bytes memory accountKey, ) = _pqcKeyStatus(account);
        if (!registered || accountKey.length == 0) revert IssuerKeyNotRegistered(account);
        if (algorithmId != ML_DSA_87) revert IssuerKeyAlgorithm(algorithmId);
        if (keccak256(accountKey) != expectedPubkeyHash) revert IssuerKeyMismatch();
        return _pqcVerify(accountKey, signature, message);
    }
}
