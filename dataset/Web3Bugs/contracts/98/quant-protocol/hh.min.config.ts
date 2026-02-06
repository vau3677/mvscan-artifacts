// hh.min.config.ts
import { HardhatUserConfig } from "hardhat/config";

const config: HardhatUserConfig = {
  solidity: {
    compilers: [
      // Match repo’s pragma (your current config uses 0.8.12)
      { version: "0.8.12", settings: { optimizer: { enabled: true, runs: 800 } } },
      // If any file needs an older/newer version, add another compiler entry here.
      // { version: "0.7.6", settings: { optimizer: { enabled: true, runs: 200 } } },
    ],
    // Optional: emit storage layout for analysis
    settings: {
      metadata: { bytecodeHash: "none" },
      optimizer: { enabled: true, runs: 800 },
      // outputSelection to ensure storageLayout (Hardhat v2.17+ picks this up)
      // @ts-ignore
      outputSelection: {
        "*": { "*": ["storageLayout", "abi", "evm.bytecode", "evm.deployedBytecode"] }
      }
    } as any
  },
  paths: {
    sources: "contracts",
    artifacts: "artifacts",
    cache: "cache"
  }
};

export default config;
