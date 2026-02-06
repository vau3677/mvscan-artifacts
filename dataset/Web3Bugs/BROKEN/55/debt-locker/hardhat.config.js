// hardhat.config.js
/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  paths: { sources: "contracts.hh" },   // only the 3 symlinked sources
  solidity: {
    compilers: [
      {
        version: "0.6.12",              // Maple v1 style contracts often use 0.6.x
        settings: {
          optimizer: { enabled: true, runs: 200 },
          outputSelection: { "*": { "*": ["abi","evm.bytecode","evm.deployedBytecode","storageLayout"] } }
        }
      },
      {
        version: "0.8.4",               // include if any file has 0.8.x pragma
        settings: {
          optimizer: { enabled: true, runs: 200 },
          outputSelection: { "*": { "*": ["abi","evm.bytecode","evm.deployedBytecode","storageLayout"] } }
        }
      }
    ]
  }
};
