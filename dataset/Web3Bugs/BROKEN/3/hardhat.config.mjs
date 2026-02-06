import { resolve } from "path";

const compilerSettings = {
  optimizer: { enabled: true, runs: 200 },
  outputSelection: {
    "*": { "*": ["abi","evm.bytecode","evm.deployedBytecode","metadata","storageLayout"] }
  },
};

export default {
  solidity: {
    compilers: [
      { version: "0.8.20", settings: compilerSettings },
      { version: "0.5.16", settings: compilerSettings }, // for uniswap v2 interfaces
    ],
  },
  paths: { sources: "contracts", artifacts: "artifacts", cache: "cache" },
};
