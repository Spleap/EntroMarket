// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract EntroMarketMockVault {
    address public immutable deployer;
    address public operator;
    string public metadataUri;

    event OperatorUpdated(address indexed oldOperator, address indexed newOperator);
    event MetadataUpdated(string oldMetadataUri, string newMetadataUri);

    constructor(address initialOperator, string memory initialMetadataUri) {
        require(initialOperator != address(0), "invalid operator");
        deployer = msg.sender;
        operator = initialOperator;
        metadataUri = initialMetadataUri;
    }

    modifier onlyDeployer() {
        require(msg.sender == deployer, "only deployer");
        _;
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
}
