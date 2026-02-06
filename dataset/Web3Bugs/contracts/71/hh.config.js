// minimal hardhat.config.js for local compile + storageLayout
require("@nomiclabs/hardhat-waffle");      // leave as-is; or migrate later
require("@nomiclabs/hardhat-web3");
require("solidity-coverage");
require("hardhat-contract-sizer");

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.7",
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: {
        "*": {
          "*": ["abi","evm.bytecode","evm.deployedBytecode","metadata","storageLayout"],
          "": ["ast"]
        }
      }
    }
  },
  networks: { hardhat: {} },               // local only; no fs reads
  paths: {
    sources: "./contracts",
    tests: "./test/unitary",
    cache: "./cache",
    artifacts: "./artifacts",
  },
  mocha: { timeout: 20000000 },
  loggingEnabled: true,
};

