#!/usr/bin/env python3
""" ISD Ablation Study """
from __future__ import annotations
import argparse, sys, os, json, re, subprocess, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from statistics import mean
from collections import defaultdict

RUNTIME_STATS = {"per_abl": defaultdict(list), "all": []}
SKIP_DIRS = {
    "repo",
    "node_modules", ".pnpm-store", ".pnpm", ".yarn", ".yarn-cache", ".yarnrc", ".yarnrc.yml",
    ".yarn/releases", ".yarn/cache", ".yarn/plugins", ".yarn/unplugged", "vendor", "hh-cache",
    "artifacts", "artifacts-zk", "cache", "cache_hardhat", "cache-foundry", ".foundry-cache",
    "out", "out-debug", "out-release", "build", "build-info", "dist", "bin", "target",
    "types", "typings", "typechain", "typechain-types", "abis", "abi", "generated", "gen",
    "deployments", "deploy", "broadcast", "flattened", "flats", "coverage", "coverage-data",
    "coverage-ts", "coverage-sol", "lcov-report", "reports", "report", "gas-snapshot",
    "gas-snapshots", "traces", "trace", "cache_broadcast", "brand-assets", "customswap",
    "tge", "vesting", "royalty-vault", "vader-bond"
    ".git", ".github", ".gitlab", ".gitlab-ci", ".circleci", ".husky", ".vscode", ".idea",
    ".devcontainer", ".codesandbox", ".editorconfig", ".prettier", ".prettier-cache",
    ".eslintcache", ".cache", ".parcel-cache",
    "docs", "documentation", "doc", "guide", "guides", "website", "site", "static", "public",
    "assets", "images", "img", "media", "design", "storybook", "diagrams", "discord-export",
    "packages", "lib", "utilities",
    "test", "tests", "testing", "__tests__", "spec", "specs", "e2e", "integration",
    "fuzz", "fuzzing", "invariants", "property", "mocks", "mock", "fixtures",
    "examples", "example", "samples", "sample", "demo", "demos", "playground",
    "kitchen-sink", "marketing-assets", "marketing", "splits",
    "scripts", "script", "tasks", "task", "tools", "tooling", "utils", "ops",
    "venv", ".venv", "env", ".env", ".tox", ".mypy_cache", "__pycache__", ".pytest_cache",
    "openzeppelin-contracts", "openzeppelin-solidity", "@openzeppelin",
    "openzeppelin-contracts-upgradeable", "openzeppelin-upgrades",
    "solmate", "solady", "solady-extensions", "ds-test", "forge-std", "dappsys",
    "ds-auth", "ds-guard", "ds-token", "ds-proxy", "ds-note", "ds-stop", "ds-value",
    "ds-math", "ds-roles",
    "prb-math", "prb-test", "abdk-libraries-solidity", "fixed-point", "solidity-bytes-utils",
    "chainlink", "@chainlink", "smartcontractkit", "chainlink-brownie-contracts",
    "uniswap-v2-core", "uniswap-v2-periphery", "uniswap-v3-core", "uniswap-v3-periphery", "@uniswap",
    "sushiswap", "sushi", "trident", "pancakeswap", "balancer-core", "balancer-v2", "balancer-labs",
    "curve", "curve-dao-contracts", "curve-factory", "convex", "bancor", "bancor-v3",
    "compound-protocol", "compound-v2", "compound-v3", "aave-protocol", "aave-v2", "aave-v3",
    "aave-v3-core", "aave-v3-periphery", "makerdao", "dss", "yield-protocol", "arbitrum-lpt-bridge",
    "optimism", "op-stack", "arbitrum", "scroll-tech", "polygon-pos", "polygon-zkevm",
    "zksync", "starknet", "gnosis", "gnosis-safe", "safe-contracts",
    "seaport", "opensea-seaport", "looksrare", "blur-protocol", "x2y2-eth",
    "weth9", "weth", "wmatic", "wnear", "wrbtc",
    "perp", "dydx", "dydx-v3", "kwenta", "perennial",
    "openzeppelin-labs", "solcurity", "openzeppelin-defender", "solhint", "solhint-plugin",
    "hardhat-deploy", "hardhat-deploy-ethers", "hardhat-deploy-tenderly", "tenderly",
    "foundry-devops", "forge-std", "ds-cheatcodes",
    "audit", "audits", "security", "reports-security",
    "node", ".gradle", "gradle", ".sbt", "target", "classes", "cmake-build-debug",
}
SKIP_DIRS = {s.lower() for s in SKIP_DIRS}
BUILD_FILES = ("hardhat.config.js", "hardhat.config.ts", "hardhat.tmp.config.js")

ENV_BASE = {"HARDHAT_TELEMETRY_DISABLED": "1"}
TAIL_RE = re.compile(
    r"""\.\s*analyzed\s*\(\s*(\d+)\s+contracts?\s+with\s+(\d+)\s+detectors?\s*\),
        \s*(\d+)\s+result\(s\)\s+found""", re.I | re.X,
)
DEFAULT_RESULTS_FILE = Path("./out/done.tsv")
FOUNDRY = "foundry.toml"
TRUFFLE = ("truffle-config.js", "truffle.js")
BROWNIE = ("brownie-config.yaml", "brownie-config.yml")

def red(t): return f"\033[91m{t}\033[0m"
def green(t): return f"\033[92m{t}\033[0m"
def yellow(t): return f"\033[93m{t}\033[0m"

# Helpers

# Nothing gets compiled or cleaned, but we must know how to interpret artifacts
def framework_flags(fw):
    fw = (fw or "").lower()
    if fw == "foundry": return "--foundry-ignore-compile", "--compile-force-framework foundry"
    if fw == "hardhat": return "--hardhat-ignore-compile", "--compile-force-framework hardhat"
    if fw == "truffle": return "--truffle-ignore-compile", "--compile-force-framework truffle"
    if fw == "brownie": return "--ignore-compile", "--compile-force-framework brownie"
    return "--ignore-compile", ""

# Writes the ablation index
def write_ablation_index(ablations, out_root: Path, start_index=0):
    out_root.mkdir(parents=True, exist_ok=True)
    mapping = []
    for i, abl in enumerate(ablations, start=start_index): mapping.append({"id": i, "name": abl.get("name", "unnamed"), "env": dict(sorted(abl.get("env", {}).items()))})
    (out_root / "ablation_map.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    with open(out_root / "ablation_map.tsv", "w", encoding="utf-8") as fh:
        fh.write("id\tname\tenv_json\n")
        for m in mapping: fh.write(f"{m['id']}\t{m['name']}\t{json.dumps(m['env'], separators=(',',':'), sort_keys=True)}\n")

# Detects our repo framework from hints
def detect_framework(root: Path) -> str:
    if (root / FOUNDRY).exists(): return "foundry"
    if (root / "hardhat.config.ts").exists() or (root / "hardhat.config.js").exists(): return "hardhat"
    if any((root / f).exists() for f in TRUFFLE): return "truffle"
    if any((root / f).exists() for f in BROWNIE): return "brownie"
    if any(root.glob("contracts/**/*.sol")): return "hardhat"
    if any(root.glob("src/**/*.sol")): return "foundry"
    return "hardhat"

# Finds the configuration directories within each repo
def find_config_dirs(contracts_root: Path):
    if not contracts_root.exists(): return []
    dirs=set()
    for p in contracts_root.rglob("*"):
        if not p.is_file(): continue
        if p.name in BUILD_FILES or p.name == FOUNDRY or p.name in TRUFFLE or p.name in BROWNIE: parent = p.parent.resolve()
        else: continue
        if any(part.lower() in SKIP_DIRS for part in parent.parts): continue
        has_pkg = (parent / "package.json").exists()
        has_sol = any(parent.glob("contracts/**/*.sol")) or any(parent.glob("src/**/*.sol"))
        if not (has_pkg or has_sol): continue
        dirs.add(parent)
    return sorted(dirs, key=lambda p: str(p).lower())

# Actual runtime command capture with built-in safeguards
def run_cmd_capture(cmd, cwd: Path, env=None, timeout=None):
    e = os.environ.copy()
    if env: e.update(env)
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=e, timeout=timeout)
        return proc.returncode, proc.stdout
    except subprocess.TimeoutExpired as te:
        out = (te.stdout or "") + (te.stderr or "")
        return 124, out
    except Exception as ex:
        return 255, f"[runner-exception] {ex}"

# Extracts summary from tail of analyzer (results)
def extract_tail_summary(text):
    i = None
    for line in reversed(text.splitlines()):
        i = TAIL_RE.search(line)
        if i: break
    if not i: return None
    c,d,r = i.groups()
    return f"{c}c/{d}/{r}r"

# Reads the map with the label, ablation, and summary
def read_done_map(path: Path):
    if not path.exists(): return {}
    d = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip(): continue
        parts = line.split("\t")
        if len(parts) >= 3 and not TAIL_RE.search(parts[1]):
            label, ablation, summary = parts[0], parts[1], parts[2]
            d[(label, ablation)] = summary
    return d

# Prints all required statistics for our study
def print_runtime_summary(stats: dict):
    print("\n======= RUNTIME AVERAGES =======")
    if stats["per_abl"]:
        w = max(len(k) for k in stats["per_abl"].keys())
        for name, samples in sorted(stats["per_abl"].items()):
            if samples: print(f"{name:<{w}}  n={len(samples):>4}  avg={mean(samples):8.3f}s")
    else:
        print("(no successful runs recorded)")
    if stats["all"]: print(f"\nOverall        n={len(stats['all']):>4}  avg={mean(stats['all']):8.3f}s\n")

# Pretiffies a cfg relative to a root
def prettify(cfg: Path, root: Path) -> str:
    try: return cfg.resolve().relative_to(root.resolve()).as_posix()
    except Exception: return cfg.name

# Detector run and statistics
def run(cfg_dir: Path, label, cmd, ablations, out_json_name, timeout_run, results_path: Path, stats, strict_rc=False, ablation_start_index=0):
    print(f"\n================ {label} ================")

    fw = detect_framework(cfg_dir)
    print(green(f"[INFO] Framework assumed: {fw}"))

    ignore_flag, force_flag = framework_flags(fw)
    cmd_base = cmd.strip()
    slither_base = f"{cmd_base} {ignore_flag} {force_flag}".strip()

    contract_out_base, rows = Path("out") / label, []
    for abl_idx, abl in enumerate(ablations, start=ablation_start_index):
        name = abl["name"]
        env_over = abl.get("env", {})
        env_run = os.environ.copy()
        env_run.update(ENV_BASE)
        out_dir = contract_out_base / str(abl_idx)
        out_dir.mkdir(parents=True, exist_ok=True)
        json_out_path = (out_dir / "findings.json").resolve()
        env_run["ISD_JSON_OUT"] = str(json_out_path)
        for k, v in env_over.items(): env_run[k] = v

        print(green(f"[RUNNING] {name}: {slither_base}"))
        t0 = time.time()
        rc, out = run_cmd_capture(slither_base, cwd=cfg_dir, env=env_run, timeout=timeout_run)
        elapsed = time.time() - t0

        sum_tail = extract_tail_summary(out)
        ok = (rc == 0 if strict_rc else True) and (sum_tail is not None or rc == 0)
        if sum_tail is None and rc == 0: sum_tail = "ok"

        status_line = f"{sum_tail}" if ok and rc == 0 else (f"{sum_tail} (rc={rc})" if ok else f"ERR(rc={rc})")
        printer = green if (ok and rc == 0) else (yellow if ok else red)
        print(printer(f"[{name:<18}] {status_line}  {elapsed:7.3f}s  -> {json_out_path}"))

        (out_dir / "slither_stdout.txt").write_text(out, encoding="utf-8", errors="ignore")
        meta = {
            "label": label,
            "ablation_id": abl_idx,
            "name": name,
            "env": env_over,
            "rc": rc,
            "ok": ok,
            "status_line": status_line,
            "elapsed_sec": elapsed,
            "started_unix": t0,
            "finished_unix": t0 + elapsed,
            "is_json_present": json_out_path.exists(),
        }
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

        if ok:
            stats["per_abl"][name].append(elapsed)
            stats["all"].append(elapsed)

        rows.append((f"{abl_idx}:{name}", status_line, elapsed, rc))

        results_path.parent.mkdir(parents=True, exist_ok=True)
        existing = results_path.read_text(encoding="utf-8", errors="ignore") if results_path.exists() else ""
        if existing and not existing.endswith("\n"): existing += "\n"
        line = f"{label}\t{name}\t{status_line}\t{elapsed:.3f}\t{rc}"
        tmp = results_path.with_suffix(results_path.suffix + ".tmp")
        tmp.write_text(existing + line + ("\n" if not line.endswith("\n") else ""), encoding="utf-8")
        tmp.replace(results_path)

    print("\n======= SUMMARY =======")
    w = max(len(n) for n, _, _, _ in rows) if rows else 10
    for n, s, t, rc in rows:
        print(f"{n:<{w}}  {s:<26}  {t:7.3f}s  rc={rc}")
    print(green(f"[DONE] {label}: recorded {len(rows)} ablation result(s) -> {results_path}"))

def main():
    ap = argparse.ArgumentParser(description="SI detector ablation study on compiled codebases")
    ap.add_argument("--dataset-dir", default="./Web3Bugs")
    ap.add_argument("--contracts-subdir", default="contracts")
    ap.add_argument("--out-json", default="out.json")
    ap.add_argument("--cmd", default='slither . --detect inconsistent_state')
    ap.add_argument("--timeout-run", type=int, default=600)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--results-file", default=str(DEFAULT_RESULTS_FILE))
    ap.add_argument("--abl", action="append", default=None, help='Ablation spec: NAME[:KEY=VAL[,KEY=VAL...]] (repeatable)')
    ap.add_argument("--abl-file", default=None, help='JSON file with [{"name":"...","env":{"K":"V",...}}, ...]')
    args = ap.parse_args()

    ablations=[]
    if args.abl_file:
        with open(args.abl_file, "r", encoding="utf-8") as fh:
            ablations = json.load(fh)
            for x in ablations:
                x.setdefault("name", "unnamed")
                x.setdefault("env", {})
    if args.abl:
        def parse_abl_arg(s: str) -> dict:
            name_env = s.split(":", 1)
            name = name_env[0].strip()
            env={}
            if len(name_env) == 2 and name_env[1].strip():
                for kv in name_env[1].split(","):
                    k, v = kv.split("=", 1)
                    env[k.strip()] = v.strip()
            return {"name": name, "env": env}
        for a in args.abl:
            ablations.append(parse_abl_arg(a))
    if not ablations:
        ablations = [
            {"name": "baseline",       "env": {"SINK_TEST": "value",   "DIVERGENCE_BUDGET": "1000"}},
            {"name": "no_init_only",   "env": {"INIT_ONLY_FILTER": "0","SINK_TEST": "value", "DIVERGENCE_BUDGET": "1000"}},
            {"name": "no_admin_benign","env": {"ADMIN_WRITES_BENIGN":"0","SINK_TEST":"value","DIVERGENCE_BUDGET":"1000"}},
            {"name": "sink_none",      "env": {"SINK_TEST": "none",    "DIVERGENCE_BUDGET": "1000"}},
            {"name": "sink_samevar",   "env": {"SINK_TEST": "samevar", "DIVERGENCE_BUDGET": "1000"}},
            {"name": "budget_0",       "env": {"SINK_TEST": "value",   "DIVERGENCE_BUDGET": "0"}},
            {"name": "budget_inf",     "env": {"SINK_TEST": "value",   "DIVERGENCE_BUDGET": "inf"}},
        ]

    # Persist ablation index
    write_ablation_index(ablations, Path("out"), start_index=0)
    results_path = Path(args.results_file)
    done_map = read_done_map(results_path)

    root = Path(args.dataset_dir).resolve()
    contracts_root = (root / args.contracts_subdir).resolve()
    if not contracts_root.exists():
        print(red(f"[FATAL] Contracts root not found: {contracts_root}"))
        sys.exit(2)

    cfg_dirs = find_config_dirs(contracts_root)
    if args.only:
        tokens = {t.lower() for t in args.only}
        def keep(p: Path) -> bool:
            rel = prettify(p, contracts_root).lower()
            return any(tok in rel for tok in tokens)
        cfg_dirs = [p for p in cfg_dirs if keep(p)]
        if not cfg_dirs: print(red("[FATAL] --only filtered out all config dirs")); sys.exit(2)
    print(f"[INFO] Discovered {len(cfg_dirs)} contract projects under {contracts_root}")

    # Skip projects only if all requested ablations are already recorded
    filtered = []
    for d in cfg_dirs:
        label = prettify(d, contracts_root)
        if all((label, abl["name"]) in done_map for abl in ablations):
            print(green(f"[SKIP] {label}: all {len(ablations)} ablation(s) already recorded"))
            continue
        filtered.append(d)
    cfg_dirs = filtered

    stats = RUNTIME_STATS
    try:
        for d in cfg_dirs:
            label = prettify(d, contracts_root)
            run(cfg_dir=d, label=label, cmd=args.cmd, ablations=ablations, out_json_name=args.out_json,
                timeout_run=args.timeout_run, results_path=results_path, stats=stats, ablation_start_index=0)
    except KeyboardInterrupt:
        print(red("\n[INTERRUPTED] Ctrl+C received — printing partial averages..."))
        print_runtime_summary(stats)
        return 130

    print_runtime_summary(stats)
    return 0

if __name__ == "__main__": sys.exit(main())