require("@nomicfoundation/hardhat-ethers");

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    // Cover all pragmas you’ll pull in from node_modules and your contracts:
    compilers: [
      // Uniswap V2 core uses 0.5.16
      { version: "0.5.16", settings: { optimizer: { enabled: true, runs: 200 } } },
      // Uniswap V2 periphery uses 0.6.6
      {
        version: "0.6.6",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          outputSelection: { "*": { "*": ["abi","evm.bytecode","evm.deployedBytecode","metadata","storageLayout"], "": ["ast"] } }
        }
      },
      // OZ 3.4.x is ^0.6.x → use 0.6.12
      {
        version: "0.6.12",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          outputSelection: { "*": { "*": ["abi","evm.bytecode","evm.deployedBytecode","metadata","storageLayout"], "": ["ast"] } }
        }
      },
      // Project contracts target 0.7.6
      {
        version: "0.7.6",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          outputSelection: { "*": { "*": ["abi","evm.bytecode","evm.deployedBytecode","metadata","storageLayout"], "": ["ast"] } }
        }
      }
    ]
  },
  paths: {
    sources: "./contracts",   // use Truffle’s sources as-is
    artifacts: "./artifacts",
    cache: "./cache"
  }
};

