import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { network } from "hardhat";

const { ethers } = await network.create();
const abiCoder = ethers.AbiCoder.defaultAbiCoder();

async function deployFixture() {
  const [deployer, operator, alice, bob, treasury] = await ethers.getSigners();

  const usdnb = await ethers.deployContract("USDNB", [deployer.address]);
  const entropy = await ethers.deployContract("MockERC20", [
    "Entropy Token",
    "ENTROPY",
    18,
    deployer.address,
    ethers.parseUnits("1000000000", 18),
  ]);
  const vault = await ethers.deployContract("EntroVault", [
    await usdnb.getAddress(),
    await entropy.getAddress(),
    operator.address,
    "ipfs://entromarket/mock-tee-attestation",
  ]);
  const governor = await ethers.deployContract("AgentStakingGovernor", [
    await entropy.getAddress(),
    operator.address,
    ethers.parseUnits("100000", 18),
  ]);

  return { deployer, operator, alice, bob, treasury, usdnb, entropy, vault, governor };
}

async function signWithdrawal({
  vault,
  operator,
  withdrawalId,
  recipient,
  asset,
  amount,
  expiry,
}) {
  const networkInfo = await ethers.provider.getNetwork();
  const encoded = abiCoder.encode(
    ["bytes32", "bytes32", "address", "address", "uint256", "uint256", "address", "uint256"],
    [
      await vault.WITHDRAWAL_TYPEHASH(),
      withdrawalId,
      recipient,
      asset,
      amount,
      expiry,
      await vault.getAddress(),
      networkInfo.chainId,
    ],
  );
  const digest = ethers.keccak256(encoded);
  return operator.signMessage(ethers.getBytes(digest));
}

async function signStateRoot({ vault, operator, snapshotId, merkleRoot, timestamp }) {
  const networkInfo = await ethers.provider.getNetwork();
  const encoded = abiCoder.encode(
    ["bytes32", "bytes32", "bytes32", "uint256", "address", "uint256"],
    [
      await vault.STATE_ROOT_TYPEHASH(),
      snapshotId,
      merkleRoot,
      timestamp,
      await vault.getAddress(),
      networkInfo.chainId,
    ],
  );
  const digest = ethers.keccak256(encoded);
  return operator.signMessage(ethers.getBytes(digest));
}

describe("EntroMarket local contracts", () => {
  it("mints the initial USDNB supply to the deployer", async () => {
    const { deployer, usdnb } = await deployFixture();

    assert.equal(await usdnb.symbol(), "USDNB");
    assert.equal(await usdnb.decimals(), 18n);
    assert.equal(await usdnb.totalSupply(), ethers.parseUnits("100000000", 18));
    assert.equal(
      await usdnb.balanceOf(deployer.address),
      ethers.parseUnits("100000000", 18),
    );
  });

  it("deposits assets into the vault and executes a signed withdrawal", async () => {
    const { deployer, operator, alice, bob, usdnb, entropy, vault } = await deployFixture();
    const stableDeposit = ethers.parseUnits("1000", 18);
    const entropyDeposit = ethers.parseUnits("250", 18);
    const withdrawalAmount = ethers.parseUnits("125", 18);

    await usdnb.approve(await vault.getAddress(), stableDeposit);
    await entropy.approve(await vault.getAddress(), entropyDeposit);
    await vault.depositStable(stableDeposit);
    await vault.depositEntropy(entropyDeposit);

    const withdrawalId = ethers.keccak256(ethers.toUtf8Bytes("withdrawal-1"));
    const expiry = BigInt((await ethers.provider.getBlock("latest")).timestamp + 3600);
    const signature = await signWithdrawal({
      vault,
      operator,
      withdrawalId,
      recipient: bob.address,
      asset: await usdnb.getAddress(),
      amount: withdrawalAmount,
      expiry,
    });

    await vault
      .connect(alice)
      .executeWithdrawal(
        withdrawalId,
        bob.address,
        await usdnb.getAddress(),
        withdrawalAmount,
        expiry,
        signature,
      );

    assert.equal(await usdnb.balanceOf(bob.address), withdrawalAmount);
    assert.equal(await usdnb.balanceOf(await vault.getAddress()), stableDeposit - withdrawalAmount);
    assert.equal(await vault.executedWithdrawals(withdrawalId), true);

    await assert.rejects(async () => {
      await vault.executeWithdrawal(
        withdrawalId,
        bob.address,
        await usdnb.getAddress(),
        withdrawalAmount,
        expiry,
        signature,
      );
    });
  });

  it("accepts a valid signed state root submission", async () => {
    const { operator, vault } = await deployFixture();
    const snapshotId = ethers.keccak256(ethers.toUtf8Bytes("snapshot-1"));
    const merkleRoot = ethers.keccak256(ethers.toUtf8Bytes("merkle-root-1"));
    const timestamp = BigInt((await ethers.provider.getBlock("latest")).timestamp);
    const signature = await signStateRoot({
      vault,
      operator,
      snapshotId,
      merkleRoot,
      timestamp,
    });

    await vault.submitStateRoot(snapshotId, merkleRoot, timestamp, signature);

    assert.equal(await vault.latestSnapshotId(), snapshotId);
    assert.equal(await vault.latestMerkleRoot(), merkleRoot);
    assert.equal(await vault.latestStateRootTimestamp(), timestamp);
  });

  it("tracks staking eligibility and only rewards from the reward pool", async () => {
    const { deployer, operator, alice, bob, treasury, entropy, governor } = await deployFixture();
    const minStake = ethers.parseUnits("100000", 18);
    const rewardFunding = ethers.parseUnits("5000", 18);
    const slashAmount = ethers.parseUnits("1000", 18);
    const rewardAmount = ethers.parseUnits("750", 18);

    await entropy.transfer(alice.address, minStake + slashAmount);
    await entropy.transfer(bob.address, minStake);
    await entropy.approve(await governor.getAddress(), rewardFunding);
    await governor.fundRewards(rewardFunding);

    await entropy.connect(alice).approve(await governor.getAddress(), minStake + slashAmount);
    await entropy.connect(bob).approve(await governor.getAddress(), minStake);
    await governor.connect(alice).stake(minStake + slashAmount);
    await governor.connect(bob).stake(minStake);

    assert.equal(await governor.isEligible(alice.address), true);
    assert.equal(await governor.isEligible(bob.address), true);
    assert.equal(await governor.rewardPool(), rewardFunding);

    await governor.connect(operator).slash(alice.address, slashAmount, treasury.address);
    assert.equal(await governor.stakedBalance(alice.address), minStake);
    assert.equal(await entropy.balanceOf(treasury.address), slashAmount);

    await governor.connect(operator).reward(bob.address, rewardAmount);
    assert.equal(await governor.rewardPool(), rewardFunding - rewardAmount);
    assert.equal(await entropy.balanceOf(bob.address), rewardAmount);

    await governor.connect(alice).unstake(1n);
    assert.equal(await governor.isEligible(alice.address), false);

    await assert.rejects(async () => {
      await governor.connect(operator).reward(bob.address, rewardFunding);
    });

    const retainedSlash = ethers.parseUnits("250", 18);
    await governor.connect(operator).slash(alice.address, retainedSlash, await governor.getAddress());
    assert.equal(await governor.rewardPool(), rewardFunding - rewardAmount + retainedSlash);

    const governorBalance = await entropy.balanceOf(await governor.getAddress());
    assert.equal(
      governorBalance,
      (await governor.totalStaked()) + (await governor.rewardPool()),
    );
  });
});
