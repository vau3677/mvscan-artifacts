require("@nomiclabs/hardhat-ethers");
require("@nomiclabs/hardhat-waffle");
require("solidity-coverage");
require("hardhat-gas-reporter");

module.exports = {
  solidity: {
    version: "0.8.6",
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: {
        "*": {
          "*": ["abi","evm.bytecode","evm.deployedBytecode","metadata","storageLayout"],
          "": ["ast"]
        }
      }
    }
  }
};
