require("@nomicfoundation/hardhat-ethers");

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.7",
    settings: {
      evmVersion: "london",
      optimizer: { enabled: true, runs: 400 },
      outputSelection: {
        "*": {
          "*": ["abi","evm.bytecode","evm.deployedBytecode","metadata","storageLayout"],
          "": ["ast"]
        }
      }
    }
  },
  paths: {
    sources: "./contracts",
    artifacts: "./artifacts",
    cache: "./cache"
  }
};
