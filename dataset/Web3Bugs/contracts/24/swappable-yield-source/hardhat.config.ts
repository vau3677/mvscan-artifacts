import { HardhatUserConfig } from "hardhat/config";

const config: HardhatUserConfig = {
  solidity: {
    // For a single version project
    version: "0.7.6",
    settings: {
      optimizer: { enabled: true, runs: 200 },
      // 0.7.6 predates Berlin; use Istanbul to avoid warnings/errors
      evmVersion: "istanbul",
      // Ask solc to emit storage layouts into artifacts
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
      }
    }
  }
};

export default config;

