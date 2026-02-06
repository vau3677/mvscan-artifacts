// hh.v3fix.storage.js
/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    compilers: [
      {
        version: "0.8.6",                      // your primary contracts
        settings: { optimizer: { enabled: true, runs: 200 } }
      },
      {
        version: "0.7.5",                      // Uniswap v3 core / periphery
        settings: { optimizer: { enabled: true, runs: 200 } }
      }
    ],
    outputSelection: {
      "*": {
        "*": ["abi", "evm.bytecode", "evm.deployedBytecode", "storageLayout"]
      },
      "": ["ast"]
    },
    overrides: {
      "@uniswap/v3-core/contracts/**/*.sol": {
        version: "0.7.5",
        settings: { optimizer: { enabled: true, runs: 200 } }
      },
      "@uniswap/v3-periphery/contracts/**/*.sol": {
        version: "0.7.5",
        settings: { optimizer: { enabled: true, runs: 200 } }
      },
      "contracts/external/**/*.sol": {
        version: "0.7.5",
        settings: { optimizer: { enabled: true, runs: 200 } }
      },
      "contracts/interfaces/uniV3/**/*.sol": {
        version: "0.7.5",
        settings: { optimizer: { enabled: true, runs: 200 } }
      },
      "contracts/UniswapV3Helper.sol": {
        version: "0.7.5",
        settings: { optimizer: { enabled: true, runs: 200 } }
      }
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

