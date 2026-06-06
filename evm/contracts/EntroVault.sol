// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20Minimal {
    function transfer(address to, uint256 amount) external returns (bool);

    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

contract EntroVault {
    bytes32 public constant WITHDRAWAL_TYPEHASH =
        keccak256(
            "Withdrawal(bytes32 withdrawalId,address recipient,address asset,uint256 amount,uint256 expiry,address vault,uint256 chainId)"
        );
    bytes32 public constant STATE_ROOT_TYPEHASH =
        keccak256(
            "StateRoot(bytes32 snapshotId,bytes32 merkleRoot,uint256 timestamp,address vault,uint256 chainId)"
        );

    address public immutable deployer;
    address public immutable stableToken;
    address public immutable entropyToken;
    address public operator;
    string public metadataUri;

    bytes32 public latestSnapshotId;
    bytes32 public latestMerkleRoot;
    uint256 public latestStateRootTimestamp;

    mapping(bytes32 => bool) public executedWithdrawals;

    event OperatorUpdated(address indexed oldOperator, address indexed newOperator);
    event MetadataUpdated(string oldMetadataUri, string newMetadataUri);
    event Deposited(address indexed user, address indexed asset, uint256 amount);
    event Withdrawn(
        bytes32 indexed withdrawalId,
        address indexed recipient,
        address indexed asset,
        uint256 amount
    );
    event StateRootUpdated(bytes32 indexed snapshotId, bytes32 indexed merkleRoot, uint256 timestamp);

    constructor(
        address stableTokenAddress,
        address entropyTokenAddress,
        address initialOperator,
        string memory initialMetadataUri
    ) {
        require(stableTokenAddress != address(0), "invalid stable token");
        require(entropyTokenAddress != address(0), "invalid entropy token");
        require(initialOperator != address(0), "invalid operator");
        deployer = msg.sender;
        stableToken = stableTokenAddress;
        entropyToken = entropyTokenAddress;
        operator = initialOperator;
        metadataUri = initialMetadataUri;
    }

    modifier onlyDeployer() {
        require(msg.sender == deployer, "only deployer");
        _;
    }

    function depositStable(uint256 amount) external {
        _deposit(stableToken, amount);
    }

    function depositEntropy(uint256 amount) external {
        _deposit(entropyToken, amount);
    }

    function executeWithdrawal(
        bytes32 withdrawalId,
        address recipient,
        address asset,
        uint256 amount,
        uint256 expiry,
        bytes calldata signature
    ) external {
        require(recipient != address(0), "invalid recipient");
        require(block.timestamp <= expiry, "withdrawal expired");
        require(!executedWithdrawals[withdrawalId], "withdrawal already executed");
        require(asset == stableToken || asset == entropyToken, "unsupported asset");

        bytes32 digest = _toEthSignedMessageHash(
            keccak256(
                abi.encode(
                    WITHDRAWAL_TYPEHASH,
                    withdrawalId,
                    recipient,
                    asset,
                    amount,
                    expiry,
                    address(this),
                    block.chainid
                )
            )
        );
        require(_recoverSigner(digest, signature) == operator, "invalid operator signature");

        executedWithdrawals[withdrawalId] = true;
        require(IERC20Minimal(asset).transfer(recipient, amount), "asset transfer failed");
        emit Withdrawn(withdrawalId, recipient, asset, amount);
    }

    function submitStateRoot(
        bytes32 snapshotId,
        bytes32 merkleRoot,
        uint256 timestamp,
        bytes calldata signature
    ) external {
        bytes32 digest = _toEthSignedMessageHash(
            keccak256(
                abi.encode(
                    STATE_ROOT_TYPEHASH,
                    snapshotId,
                    merkleRoot,
                    timestamp,
                    address(this),
                    block.chainid
                )
            )
        );
        require(_recoverSigner(digest, signature) == operator, "invalid operator signature");

        latestSnapshotId = snapshotId;
        latestMerkleRoot = merkleRoot;
        latestStateRootTimestamp = timestamp;
        emit StateRootUpdated(snapshotId, merkleRoot, timestamp);
    }

    function setOperator(address newOperator) external onlyDeployer {
        require(newOperator != address(0), "invalid operator");
        address oldOperator = operator;
        operator = newOperator;
        emit OperatorUpdated(oldOperator, newOperator);
    }

    function setMetadataUri(string calldata newMetadataUri) external onlyDeployer {
        string memory oldMetadataUri = metadataUri;
        metadataUri = newMetadataUri;
        emit MetadataUpdated(oldMetadataUri, newMetadataUri);
    }

    function _deposit(address asset, uint256 amount) internal {
        require(amount > 0, "invalid amount");
        require(IERC20Minimal(asset).transferFrom(msg.sender, address(this), amount), "asset transfer failed");
        emit Deposited(msg.sender, asset, amount);
    }

    function _toEthSignedMessageHash(bytes32 messageHash) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
    }

    function _recoverSigner(bytes32 digest, bytes memory signature) internal pure returns (address) {
        require(signature.length == 65, "invalid signature length");
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := mload(add(signature, 0x20))
            s := mload(add(signature, 0x40))
            v := byte(0, mload(add(signature, 0x60)))
        }
        if (v < 27) {
            v += 27;
        }
        require(v == 27 || v == 28, "invalid signature version");
        address recovered = ecrecover(digest, v, r, s);
        require(recovered != address(0), "invalid signature");
        return recovered;
    }
}
