// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./MockERC20.sol";

contract USDNB is MockERC20 {
    uint8 public constant TOKEN_DECIMALS = 18;
    uint256 public constant INITIAL_SUPPLY = 100_000_000 ether;

    constructor(address initialHolder)
        MockERC20("Entropy Zero Dollar", "USDNB", TOKEN_DECIMALS, initialHolder, INITIAL_SUPPLY)
    {}
}
