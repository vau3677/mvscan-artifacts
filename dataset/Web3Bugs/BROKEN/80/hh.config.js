// hardhat.config.js
const { subtask } = require("hardhat/config");
const { TASK_COMPILE_SOLIDITY_GET_SOURCE_PATHS } =
  require("hardhat/builtin-tasks/task-names");

// Ignore backup or stray files; hardhat compiles EVERYTHING under `contracts/` by default
// so we filter before handing files to solc.
subtask(TASK_COMPILE_SOLIDITY_GET_SOURCE_PATHS, async (_, __, runSuper) => {
  const paths = await runSuper();
  return paths.filter(p => !p.endsWith(".bak"));
});

module.exports = {
  solidity: {
    version: "0.8.6",
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode", "evm.deployedBytecode", "metadata", "storageLayout"],
          "": ["ast"]
        }
      }
    }
  },
  paths: {
    sources: "contracts",       // default; left explicit
    artifacts: "artifacts",
    cache: "cache"
  }
};
