#!/usr/bin/env bash
set -euo pipefail

# Usage: ./try_yield_versions.sh [hardhat-config.js] [max_versions_per_pkg]
CONFIG="${1:-hh.config.js}"          # or hardhat.config.js
MAX="${2:-8}"                        # try last N versions per package (major 2.x)

# Packages to try (add more if needed)
PKG1='@yield-protocol/vault-interfaces'
PKG2='@yield-protocol/utils-v2'
# Optionally include yieldspace interfaces if you import from it:
PKG3='@yield-protocol/yieldspace-interfaces'

# Helper: fetch the last N versions within major 2.x (sorted ascending)
last_versions() {
  local pkg="$1" max="$2"
  node -e '
    const [pkg,max]=process.argv.slice(1);
    const {spawnSync}=require("child_process");
    const r=spawnSync("npm",["view",pkg,"versions","--json"],{encoding:"utf8"});
    if(r.status!==0){ process.exit(1); }
    let v=JSON.parse(r.stdout||"[]");
    if(!Array.isArray(v)) v=[v];
    // keep only 2.x.x
    v=v.filter(s=>/^2\.\d+\.\d+$/.test(s));
    // sort semver ascending
    v=v.sort((a,b)=>{
      const pa=a.split(".").map(Number), pb=b.split(".").map(Number);
      for(let i=0;i<3;i++){ if(pa[i]!==pb[i]) return pa[i]-pb[i]; }
      return 0;
    });
    // take last N
    v=v.slice(-Number(max));
    console.log(v.join(" "));
  ' "$pkg" "$max"
}

V1=( $(last_versions "$PKG1" "$MAX") )
V2=( $(last_versions "$PKG2" "$MAX") )
V3=( $(last_versions "$PKG3" "$MAX") )

echo "Config: $CONFIG"
echo "$PKG1 candidates: ${V1[*]:-<none>}"
echo "$PKG2 candidates: ${V2[*]:-<none>}"
echo "$PKG3 candidates: ${V3[*]:-<none>}"

# Try 2-package combos first (PKG1 x PKG2). If you need PKG3 too, the script falls back to 3-way.
try_compile() {
  local msg="$1"
  echo "==> $msg"
  # hard reset build dirs to avoid stale artifacts
  npx hardhat clean --config "$CONFIG" >/dev/null 2>&1 || true
  if npx hardhat compile --config "$CONFIG"; then
    echo "✅ SUCCESS: $msg"
    return 0
  else
    echo "❌ FAIL: $msg"
    return 1
  fi
}

# Save/restore package.json & lockfile so we don't corrupt your constraints
cp package.json package.json.bak
cp package-lock.json package-lock.json.bak 2>/dev/null || true

cleanup() {
  mv -f package.json.bak package.json 2>/dev/null || true
  mv -f package-lock.json.bak package-lock.json 2>/dev/null || true
}
trap cleanup EXIT

# Prefer exact installs to avoid drifting versions
install_exact() {
  npm install --no-audit --no-fund --save-exact "$@" >/dev/null
}

echo
echo "==== Trying 2-way combos: $PKG1 x $PKG2 (from newest backwards) ===="
for v1 in $(printf "%s\n" "${V1[@]}" | tac); do
  for v2 in $(printf "%s\n" "${V2[@]}" | tac); do
    echo
    echo "Installing: $PKG1@$v1  $PKG2@$v2"
    install_exact "$PKG1@$v1" "$PKG2@$v2" || { echo "install failed, skipping"; continue; }
    if try_compile "$PKG1@$v1 + $PKG2@$v2"; then
      echo "🎉 Best combo found:"
      echo "    $PKG1@$v1"
      echo "    $PKG2@$v2"
      exit 0
    fi
  done
done

echo
echo "==== Trying 3-way combos: $PKG1 x $PKG2 x $PKG3 (newest backwards) ===="
for v1 in $(printf "%s\n" "${V1[@]}" | tac); do
  for v2 in $(printf "%s\n" "${V2[@]}" | tac); do
    for v3 in $(printf "%s\n" "${V3[@]}" | tac); do
      echo
      echo "Installing: $PKG1@$v1  $PKG2@$v2  $PKG3@$v3"
      install_exact "$PKG1@$v1" "$PKG2@$v2" "$PKG3@$v3" || { echo "install failed, skipping"; continue; }
      if try_compile "$PKG1@$v1 + $PKG2@$v2 + $PKG3@$v3"; then
        echo "�� Best combo found:"
        echo "    $PKG1@$v1"
        echo "    $PKG2@$v2"
        echo "    $PKG3@$v3"
        exit 0
      fi
    done
  done
done

echo "💥 No working combo found within the last $MAX versions."
exit 1

