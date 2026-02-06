/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    compilers: [
      { version: "0.8.6", settings: { optimizer: { enabled: true, runs: 1000 }, metadata: { bytecodeHash: "none" } } },
      { version: "0.7.6", settings: { optimizer: { enabled: true, runs: 800  },  metadata: { bytecodeHash: "none" } } }
    ],
    // root-level outputSelection so solc emits storage layouts into build-info
    outputSelection: {
      "*": { "*": ["abi","evm.bytecode","evm.deployedBytecode","storageLayout"] },
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
