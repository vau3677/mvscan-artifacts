// find_yield_imports.js

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

// List of contract import strings (these are the import specifiers you saw)
const imports = [
  "@yield-protocol/utils-v2/contracts/token/IERC20.sol",
  "@yield-protocol/utils-v2/contracts/token/ERC20.sol",
  "@yield-protocol/utils-v2/contracts/access/AccessControl.sol",
  "@yield-protocol/utils-v2/contracts/token/TransferHelper.sol",
  "@yield-protocol/vault-interfaces/ICauldron.sol",
  "@yield-protocol/vault-interfaces/DataTypes.sol",
  "@yield-protocol/vault-interfaces/IOracle.sol",
  "@yield-protocol/utils-v2/contracts/cast/CastBytes32Bytes6.sol",
  "@yield-protocol/utils-v2/contracts/token/IWETH9.sol"
];

// Base directory to search (node_modules/@yield-protocol)
const base = path.join(process.cwd(), "node_modules", "@yield-protocol");

function findImport(importPath) {
  // derive the last path segment (filename)
  const fname = importPath.split("/").pop();
  try {
    // Use grep recursively under base
    const cmd = `grep -R "${fname}" -n "${base}"`;
    const out = execSync(cmd, { encoding: "utf-8" });
    return out.trim().split("\n");
  } catch (e) {
    // No match
    return [];
  }
}

console.log("Searching locations in node_modules for imports:");
for (const imp of imports) {
  console.log(`\nImport: ${imp}`);
  const results = findImport(imp);
  if (results.length === 0) {
    console.log("  → Not found in node_modules/@yield-protocol");
  } else {
    for (const r of results) {
      console.log("  → " + r);
    }
  }
}

