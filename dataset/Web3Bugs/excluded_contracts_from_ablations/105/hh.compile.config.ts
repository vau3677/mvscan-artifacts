// hh.compile.config.ts
import { HardhatUserConfig } from "hardhat/config";

const config: HardhatUserConfig = {
  paths: {
    sources: "contracts",
    artifacts: "artifacts",
    cache: "cache",
  },
  solidity: {
    compilers: [
      {
        version: "0.8.20",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          metadata: { bytecodeHash: "ipfs" },
          outputSelection: {
            "*": {
              "": ["metadata"],           // keep default outputs
              "*": [
                "abi",
                "evm.bytecode",
                "evm.bytecode.sourceMap",
                "evm.deployedBytecode",
                "evm.deployedBytecode.sourceMap",
                "storageLayout"            // << include storage layout
              ]
            }
          },
        },
      },
      {
        version: "0.6.12",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          metadata: { bytecodeHash: "ipfs" },
          outputSelection: {
            "*": {
              "": ["metadata"],
              "*": [
                "abi",
                "evm.bytecode",
                "evm.bytecode.sourceMap",
                "evm.deployedBytecode",
                "evm.deployedBytecode.sourceMap",
                "storageLayout"
              ]
            }
          },
        },
      },
    ],
    // Optionally, you could add overrides here if some files need a different setup
  },
  // No networks
};

export default config;
