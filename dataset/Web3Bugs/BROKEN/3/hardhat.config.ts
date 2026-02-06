import { HardhatUserConfig } from "hardhat/config";

/**
 * Tip: Hardhat auto-downloads matching solc versions.
 * If your files use one pragma version (e.g., ^0.8.19), set that here.
 * If there are mixed pragmas, see the "Mixed pragma" section below.
 */

const config: HardhatUserConfig = {
  solidity: {
    // Single-pragma default. Change to your repo's pragma if different.
    version: "0.8.20",
    settings: {
      optimizer: { enabled: true, runs: 200 },
      // <- THIS is the crucial part for Slither 0.9.2:
      outputSelection: {
        "*": { "*": ["abi", "evm.bytecode", "evm.deployedBytecode", "metadata", "storageLayout"] }
      }
    },
  },
  paths: {
    sources: "contracts",
    artifacts: "artifacts",
    cache: "cache",
  }
};

export default config;
