/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  // Minimal compiler pin that matches the repo (0.8.13)
  solidity: {
    compilers: [
      {
        version: "0.8.13",
        settings: {
          optimizer: { enabled: true, runs: 10000 },
          metadata: { bytecodeHash: "none" }
        }
      }
    ],
    // IMPORTANT: ask solc to emit storage layouts in artifacts/build-info
    outputSelection: {
      "*": {
        "*": ["abi", "evm.bytecode", "evm.deployedBytecode", "storageLayout"]
      },
      "": ["ast"]
    }
  },
  paths: {
    sources: "contracts",
    artifacts: "artifacts",
    cache: "cache",
    tests: "test"
  },
  mocha: { timeout: 1_000_000 }
};
