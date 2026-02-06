// require("@nomiclabs/hardhat-ethers");
// const { subtask } = require("hardhat/config");
// const { TASK_COMPILE_SOLIDITY_GET_SOURCE_PATHS } = require("hardhat/builtin-tasks/task-names");

// subtask(TASK_COMPILE_SOLIDITY_GET_SOURCE_PATHS, async (_, __, runSuper) => {
//   const paths = await runSuper();
//   return paths.filter(p => !p.includes("contracts/outside-scope/"));
// });

// module.exports = {
//   solidity: {
//     version: "0.8.3",
//     settings: {
//       optimizer: { enabled: false, runs: 200 },
//       outputSelection: { "*": { "*": ["storageLayout", "abi", "evm.bytecode"] } } // needed for layouts
//     }
//   },
//   paths: { sources: "contracts", artifacts: "artifacts", cache: "cache" }
// };
require("@nomiclabs/hardhat-ethers");

module.exports = {
  solidity: {
    version: "0.8.3",
    settings: {
      optimizer: { enabled: false, runs: 200 },
      outputSelection: {
        "*": { "*": ["storageLayout", "abi", "evm.bytecode"] }
      }
    }
  },
  networks: {
    hardhat: {
      // <-- THIS LINE UNBLOCKS YOUR DEPLOY
      allowUnlimitedContractSize: true
    }
  },
  paths: {
    sources: "contracts",
    artifacts: "artifacts",
    cache: "cache"
  }
};