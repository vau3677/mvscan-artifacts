module.exports = {
  solidity: {
    compilers: [
      { version: "0.8.7",  settings: { optimizer: { enabled: true, runs: 200 } } },
      { version: "0.8.0",  settings: { optimizer: { enabled: true, runs: 200 } } }, // for ^0.8.0
      { version: "0.6.12", settings: { optimizer: { enabled: true, runs: 200 } } },
      { version: "0.6.11", settings: { optimizer: { enabled: true, runs: 200 } } },
      { version: "0.5.17", settings: { optimizer: { enabled: true, runs: 200 } } }, // for >=0.5.0
      { version: "0.4.26", settings: { optimizer: { enabled: true, runs: 200 } } }, // for ^0.4.23
    ],
    overrides: {
      // path relative to `paths.sources` below
      "TestContracts/DappSys/proxy.sol": {
        version: "0.4.26",
        settings: { optimizer: { enabled: true, runs: 200 } }
      }
    }
  },
  paths: {
    sources:   "packages/contracts/contracts",
    artifacts: "packages/contracts/artifacts",
    cache:     "packages/contracts/cache"
  }
};
