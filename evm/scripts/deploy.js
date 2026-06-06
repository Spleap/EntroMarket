import dotenv from "dotenv";
import { network } from "hardhat";

dotenv.config({ path: "../../.env" });

async function main() {
  const { ethers } = await network.connect();
  const [deployer] = await ethers.getSigners();
  const balanceBefore = await ethers.provider.getBalance(deployer.address);

  console.log("Deploying with address:", deployer.address);
  console.log("Balance before:", ethers.formatEther(balanceBefore), "ETH");

  const operator = process.env.OPERATOR_ADDRESS || deployer.address;
  const metadataUri =
    process.env.METADATA_URI || "ipfs://entromarket/mock-tee-attestation";
  const entropySupply = process.env.ENTROPY_INITIAL_SUPPLY || "1000000000";
  const minAgentStake = process.env.MIN_AGENT_STAKE || "100000";

  const usdnbFactory = await ethers.getContractFactory("USDNB");
  const usdnb = await usdnbFactory.deploy(deployer.address);
  await usdnb.waitForDeployment();

  const mockErc20Factory = await ethers.getContractFactory("MockERC20");
  const entropy = await mockErc20Factory.deploy(
    "Entropy Token",
    "ENTROPY",
    18,
    deployer.address,
    ethers.parseUnits(entropySupply, 18),
  );
  await entropy.waitForDeployment();

  const vaultFactory = await ethers.getContractFactory("EntroVault");
  const vault = await vaultFactory.deploy(
    await usdnb.getAddress(),
    await entropy.getAddress(),
    operator,
    metadataUri,
  );
  await vault.waitForDeployment();

  const governorFactory = await ethers.getContractFactory("AgentStakingGovernor");
  const governor = await governorFactory.deploy(
    await entropy.getAddress(),
    operator,
    ethers.parseUnits(minAgentStake, 18),
  );
  await governor.waitForDeployment();

  const deploymentTx = vault.deploymentTransaction();
  const balanceAfter = await ethers.provider.getBalance(deployer.address);

  console.log("USDNB:", await usdnb.getAddress());
  console.log("USDNB supply:", "100000000");
  console.log("ENTROPY:", await entropy.getAddress());
  console.log(
    "ENTROPY supply:",
    ethers.formatUnits(ethers.parseUnits(entropySupply, 18), 18),
  );
  console.log("Vault:", await vault.getAddress());
  console.log("AgentStakingGovernor:", await governor.getAddress());
  console.log("Operator:", operator);
  console.log("Min agent stake:", minAgentStake, "ENTROPY");
  console.log("Metadata URI:", metadataUri);
  console.log("Tx hash:", deploymentTx.hash);
  console.log("Balance after:", ethers.formatEther(balanceAfter), "ETH");
  console.log("Suggested env updates:");
  console.log("  USDNB_TOKEN_ADDRESS=", await usdnb.getAddress());
  console.log("  ENTROPY_TOKEN_ADDRESS=", await entropy.getAddress());
  console.log("  ENTRO_VAULT_ADDRESS=", await vault.getAddress());
  console.log("  AGENT_STAKING_GOVERNOR_ADDRESS=", await governor.getAddress());
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
