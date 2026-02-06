// hardhat.config.js
/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.17",
    settings: {
      optimizer: { enabled: true, runs: 3000 },
      outputSelection: { "*": { "*": ["storageLayout"] } }, // <-- key line
    },
  },
  paths: { sources: "./src" },
};

