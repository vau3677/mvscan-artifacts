// hh.storage.cjs  (no require("hardhat") here)
module.exports = {
  solidity: {
    version: "0.8.10",
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: {
        "*": {
          "*": [
            "abi",
            "evm.bytecode",
            "evm.deployedBytecode",
            "metadata",
            "storageLayout"
          ],
          "": ["ast"]
        }
      },
      evmVersion: "london"
    }
  },
  paths: {
    sources: "./contracts",
    artifacts: "./artifacts-storage",
    cache: "./cache-storage"
  }
};
