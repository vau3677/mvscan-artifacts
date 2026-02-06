require("dotenv").config();
require("@nomicfoundation/hardhat-ethers");     // <- ethers plugin
require("@openzeppelin/hardhat-upgrades");      // ok to keep; not required for compile
require("hardhat-gas-reporter");                // unused on compile, harmless

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    // If some test stubs use older pragmas, list extra compilers here.
    compilers: [
      {
        version: "0.8.4",
        settings: {
          optimizer: { enabled: true, runs: 1000 },
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
      },
      // add only if you hit pragma-mismatch errors in /testing stubs:
      // { version: "0.6.12", settings: { optimizer: { enabled: true, runs: 200 } } }
    ],
  },

  // (Optional) keep networks; compile doesn't use them
  networks: {
    hardhat: { },
  },

  // Make paths explicit (recurses into subfolders like ./contracts/solidity/**)
  paths: {
    sources: "./contracts",
    artifacts: "./artifacts",
    cache: "./cache",
  },
};
