import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-foundry";

// If you installed classic HH2 plugins, keep the minimum you need.
// Avoid importing project-specific files (no './utils/wallet' here).
import "@nomiclabs/hardhat-ethers";          // or @nomicfoundation/hardhat-ethers if you chose that line
// import "@nomiclabs/hardhat-etherscan";    // not needed for compile
// import "@openzeppelin/hardhat-upgrades";  // not needed for compile

const outputSelection = {
  "*": {
    "*": [
      "abi",
      "evm.bytecode",
      "evm.deployedBytecode",
      "metadata",
      "devdoc",
      "userdoc",
      "storageLayout"
    ],
    "": ["ast"]
  }
};

const config: HardhatUserConfig = {
  solidity: {
    compilers: [
      { version: "0.8.20", settings: { optimizer: { enabled: true, runs: 200 }, outputSelection } },
      { version: "0.7.6",  settings: { optimizer: { enabled: true, runs: 200 }, outputSelection } },
      { version: "0.6.12", settings: { optimizer: { enabled: true, runs: 200 }, outputSelection } }
    ],
  },
  paths: {
    sources: "contracts_src",
    artifacts: "artifacts",
    cache: "cache",
    tests: "test"
  }
};

export default config;

