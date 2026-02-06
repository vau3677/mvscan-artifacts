/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    compilers: [
      { version: "0.8.6", settings: { optimizer: { enabled: true, runs: 2000 }, metadata: { bytecodeHash: "none" } } }
    ],
    outputSelection: {
      "*": { "*": ["abi","evm.bytecode","evm.deployedBytecode","storageLayout"] },
      "": ["ast"]
    }
  },
  paths: {
    sources: ".",           // <— key difference
    artifacts: "artifacts",
    cache: "cache",
    tests: "test"
  }
};
