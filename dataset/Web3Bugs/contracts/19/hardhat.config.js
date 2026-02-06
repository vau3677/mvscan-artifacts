require("@nomicfoundation/hardhat-ethers");

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    // exact 0.8.4 to match the pragma
    compilers: [{
      version: "0.8.4",
      settings: {
        optimizer: { enabled: true, runs: 200 },
        outputSelection: {
          "*": {
            "*": ["abi","evm.bytecode","evm.deployedBytecode","metadata","storageLayout"],
            "": ["ast"]
          }
        }
      }
    }]
  },
  paths: {
    sources: "./contracts",
    artifacts: "./artifacts",
    cache: "./cache"
  }
};
