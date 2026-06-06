// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20StakeToken {
    function transfer(address to, uint256 amount) external returns (bool);

    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

contract AgentStakingGovernor {
    address public immutable deployer;
    address public immutable entropyToken;
    uint256 public immutable minStake;
    address public operator;
    uint256 public totalStaked;
    uint256 public rewardPool;

    mapping(address => uint256) public stakedBalance;

    event OperatorUpdated(address indexed oldOperator, address indexed newOperator);
    event RewardPoolFunded(address indexed funder, uint256 amount, uint256 totalRewardPool);
    event Staked(address indexed agent, uint256 amount, uint256 totalStakedByAgent);
    event Unstaked(address indexed agent, uint256 amount, uint256 totalStakedByAgent);
    event Slashed(address indexed agent, address indexed recipient, uint256 amount);
    event Rewarded(address indexed agent, uint256 amount);

    constructor(address entropyTokenAddress, address initialOperator, uint256 minimumStake) {
        require(entropyTokenAddress != address(0), "invalid entropy token");
        require(initialOperator != address(0), "invalid operator");
        require(minimumStake > 0, "invalid minimum stake");
        deployer = msg.sender;
        entropyToken = entropyTokenAddress;
        operator = initialOperator;
        minStake = minimumStake;
    }

    modifier onlyDeployer() {
        require(msg.sender == deployer, "only deployer");
        _;
    }

    modifier onlyOperator() {
        require(msg.sender == operator || msg.sender == deployer, "only operator");
        _;
    }

    function stake(uint256 amount) external {
        require(amount > 0, "invalid amount");
        stakedBalance[msg.sender] += amount;
        totalStaked += amount;
        require(
            IERC20StakeToken(entropyToken).transferFrom(msg.sender, address(this), amount),
            "stake transfer failed"
        );
        emit Staked(msg.sender, amount, stakedBalance[msg.sender]);
    }

    function fundRewards(uint256 amount) external {
        require(amount > 0, "invalid amount");
        rewardPool += amount;
        require(
            IERC20StakeToken(entropyToken).transferFrom(msg.sender, address(this), amount),
            "reward funding transfer failed"
        );
        emit RewardPoolFunded(msg.sender, amount, rewardPool);
    }

    function unstake(uint256 amount) external {
        require(amount > 0, "invalid amount");
        require(stakedBalance[msg.sender] >= amount, "insufficient staked balance");
        stakedBalance[msg.sender] -= amount;
        totalStaked -= amount;
        require(IERC20StakeToken(entropyToken).transfer(msg.sender, amount), "unstake transfer failed");
        emit Unstaked(msg.sender, amount, stakedBalance[msg.sender]);
    }

    function slash(address agent, uint256 amount, address recipient) external onlyOperator {
        require(agent != address(0), "invalid agent");
        require(recipient != address(0), "invalid recipient");
        require(amount > 0, "invalid amount");
        require(stakedBalance[agent] >= amount, "insufficient staked balance");
        stakedBalance[agent] -= amount;
        totalStaked -= amount;
        if (recipient == address(this)) {
            rewardPool += amount;
        } else {
            require(IERC20StakeToken(entropyToken).transfer(recipient, amount), "slash transfer failed");
        }
        emit Slashed(agent, recipient, amount);
    }

    function reward(address agent, uint256 amount) external onlyOperator {
        require(agent != address(0), "invalid agent");
        require(amount > 0, "invalid amount");
        require(rewardPool >= amount, "insufficient reward pool");
        rewardPool -= amount;
        require(IERC20StakeToken(entropyToken).transfer(agent, amount), "reward transfer failed");
        emit Rewarded(agent, amount);
    }

    function isEligible(address agent) external view returns (bool) {
        return stakedBalance[agent] >= minStake;
    }

    function setOperator(address newOperator) external onlyDeployer {
        require(newOperator != address(0), "invalid operator");
        address oldOperator = operator;
        operator = newOperator;
        emit OperatorUpdated(oldOperator, newOperator);
    }
}
