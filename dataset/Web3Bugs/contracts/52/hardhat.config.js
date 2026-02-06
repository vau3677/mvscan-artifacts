module.exports = {
  paths: {
    sources: "./contracts",
    artifacts: "./artifacts",
    cache: "./cache",
    tests: "./__skip_tests__" // keep HH from scanning tests
  },
  solidity: {
    compilers: [
      {
        version: "0.8.9",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          // ask solc for storageLayout explicitly
          outputSelection: { "*": { "*": ["abi","evm.bytecode","evm.deployedBytecode","storageLayout"] } }
        }
      }
    ]
  }
};
