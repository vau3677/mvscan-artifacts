// Minimal Hardhat config focused on storageLayout output (no plugins)
module.exports = {
  paths: {
    sources: "./contracts",
    artifacts: "./artifacts",
    cache: "./cache",
  },
  solidity: {
    compilers: [
      {
        version: "0.6.12",
        settings: {
          metadata: { bytecodeHash: "none" },
          optimizer: { enabled: true, runs: 800 },
          outputSelection: {
            "*": {
              "*": ["abi", "evm.bytecode", "evm.deployedBytecode", "metadata", "storageLayout"],
              "": ["ast"],
            },
          },
        },
      },
      {
        version: "0.8.11",
        settings: {
          metadata: { bytecodeHash: "none" },
          optimizer: { enabled: true, runs: 800 },
          outputSelection: {
            "*": {
              "*": ["abi", "evm.bytecode", "evm.deployedBytecode", "metadata", "storageLayout"],
              "": ["ast"],
            },
          },
        },
      },
    ],
  },
};
