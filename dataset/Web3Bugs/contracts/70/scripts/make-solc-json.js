// scripts/make-solc-json.js
const fs = require('fs'), path = require('path');

function listSol(dir) {
  const out = [];
  (function walk(d){
    for (const f of fs.readdirSync(d)) {
      const p = path.join(d, f);
      const s = fs.statSync(p);
      if (s.isDirectory()) walk(p);
      else if (f.endsWith('.sol')) out.push(p.replace(/\\/g,'/'));
    }
  })(dir);
  return out;
}

const roots = ['contracts']; // keep it minimal; compile vader-bond separately if needed
const files = roots.flatMap(listSol);

// Build Standard JSON input
const input = {
  language: "Solidity",
  sources: Object.fromEntries(
    files.map(f => [f, { urls: [f] }])   // let solc read files from disk
  ),
  settings: {
    optimizer: { enabled: true, runs: 200 },
    // remap OZ style imports
    remappings: ["@openzeppelin/=node_modules/@openzeppelin/"],
    outputSelection: { "*": { "*": ["storageLayout"] } }
  }
};

fs.mkdirSync('build/storage', { recursive: true });
fs.writeFileSync('build/storage/in.json', JSON.stringify(input));
console.log('Wrote build/storage/in.json with', files.length, 'sources');

