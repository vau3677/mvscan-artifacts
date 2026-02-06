// hh.v6.storage.config.js
/** @type import('hardhat/config').HardhatUserConfig */
const config = {
  solidity: {
    // Keep one compiler unless you truly need multiple
    compilers: [
      {
        version: "0.6.12",
        settings: {
          optimizer: { enabled: true, runs: 1337 },
          metadata: { bytecodeHash: "none" }
        }
      }
    ],
    // IMPORTANT: outputSelection must live at the `solidity` root when using compilers[]
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

module.exports = config;
