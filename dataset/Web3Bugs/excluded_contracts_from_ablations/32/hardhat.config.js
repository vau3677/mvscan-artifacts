require("@nomiclabs/hardhat-ethers");

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    compilers: [
      {
        version: "0.8.6",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          outputSelection: {
            "*": {
              "*": ["abi", "evm.bytecode", "evm.deployedBytecode", "metadata", "storageLayout"],
              "": ["ast"],
            },
          },
        },
      },
      {
        version: "0.7.6",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          outputSelection: {
            "*": {
              "*": ["abi", "evm.bytecode", "evm.deployedBytecode", "metadata", "storageLayout"],
              "": ["ast"],
            },
          },
        },
      },
    ],
    // Force specific compiler for Uniswap v3 + any of your 0.7.x local interfaces/helpers
    overrides: {
      "@uniswap/v3-core/contracts/**/*.sol": {
        version: "0.7.6",
        settings: { optimizer: { enabled: true, runs: 200 } },
      },
      "@uniswap/v3-periphery/contracts/**/*.sol": {
        version: "0.7.6",
        settings: { optimizer: { enabled: true, runs: 200 } },
      },
      "contracts/external/**/*.sol": {
        version: "0.7.6",
        settings: { optimizer: { enabled: true, runs: 200 } },
      },
      "contracts/interfaces/uniV3/**/*.sol": {
        version: "0.7.6",
        settings: { optimizer: { enabled: true, runs: 200 } },
      },
      "contracts/UniswapV3Helper.sol": {
        version: "0.7.6",
        settings: { optimizer: { enabled: true, runs: 200 } },
      },
    },
  },
};
