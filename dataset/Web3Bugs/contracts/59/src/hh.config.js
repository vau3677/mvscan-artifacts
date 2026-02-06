require("@nomicfoundation/hardhat-ethers");

/** Minimal Hardhat config for Malt-like repo */
module.exports = {
  solidity: {
    compilers: [
      // UniswapV2Library.sol
      {
        version: "0.5.16",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          outputSelection: {
            "*": { "*": ["abi", "evm.bytecode", "evm.deployedBytecode", "metadata", "storageLayout"] }
          }
        }
      },
      // Primary project + interfaces (>=0.6.6)
      {
        version: "0.6.6",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          outputSelection: {
            "*": { "*": ["abi", "evm.bytecode", "evm.deployedBytecode", "metadata", "storageLayout"] }
          }
        }
      },
      // Covers “<0.8.0” contracts and OZ dependencies
      {
        version: "0.6.12",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          outputSelection: {
            "*": { "*": ["abi", "evm.bytecode", "evm.deployedBytecode", "metadata", "storageLayout"] }
          }
        }
      }
    ]
  },
  paths: {
    sources: "./contracts",
    artifacts: "./artifacts",
    cache: "./cache"
  }
};
