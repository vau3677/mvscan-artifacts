/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    compilers: [
      {
        version: "0.6.12",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          outputSelection: { "*": { "*": ["abi","evm.bytecode","evm.deployedBytecode","metadata","storageLayout"], "": ["ast"] } }
        }
      },
      {
        version: "0.6.10",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          outputSelection: { "*": { "*": ["abi","evm.bytecode","evm.deployedBytecode","metadata","storageLayout"], "": ["ast"] } }
        }
      }
    ]
  },
  paths: { sources: "./contracts" }
};
