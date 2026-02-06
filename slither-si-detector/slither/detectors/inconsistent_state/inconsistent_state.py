"""
MV-Scan (Multi-Variable State-Inconsistency Detection)
Author: Vladislav Usatii (vau3677@rit.edu)

Goals:
- Build an SDG over the compilation and its storage layout.
- Keep only the CFG blocks that are reachable from user-callable entrypoints.
- Detect the stale-read/destructive-write pattern and group entangled variables instead of just the primary variable.
- Bucket by transaction-sets and variables so that we can track multi-variable groupings.
- Emit stable JSON for a future dynamic exploit generator (future work).

Non-goals:
- We do not attempt to perfectly catch SI bugs or improve static SV-SI detection.

Extensions:
- Storage-slot aliasing (eliminates FP where unique variables share slots).
- Pseudo-variables for branch-groups and multi-returns (to track MV-SI).
- Reentrant and shared-callee shape tags to guide validation/fuzzing.
- A basic “atomic group” merging of entrypoints (to support above-transaction work).

Usage:
1. Add storageLayout to the configuration of the analyzed codebase to track slots.
2. Run npx hardhat clean && npx hardhat compile on the new configuration.
3. Use ISD_JSON_OUT=out.json slither . --detect inconsistent_state --hardhat-ignore-compile
3a. ISD_JSON_OUT is the filename of the JSON output.
3b. --hardhat-ignore-compile skips npx hardhat clean/compile, which is crucial if you want the detector to pick up slots.
"""
import json, os, glob, pathlib, subprocess, sys
from typing import List, Set, Dict, Tuple
from collections import defaultdict, deque
from eth_utils import keccak
from eth_abi import encode
from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification
from slither.utils.output import Output
from slither.core.variables import StateVariable
from slither.core.declarations.function_contract import FunctionContract
from slither.core.source_mapping.source_mapping import Source
from slither.slithir.operations import HighLevelCall, InternalCall, Assignment
from .utils.sdg import (SDG, stale_read_pairs, BasicBlock, ExternalStateVar, MappingSlotVar, branch_types, reachable_without_overwrite, var_key_txt)

# Parses DIVERGENCE_BUDGET (0: no traversal | 0<n<inf bounds to n | None: unbounded)
def _parse_divergence_budget():
    budget = os.getenv("DIVERGENCE_BUDGET", str(1000)).strip().lower()
    if budget in {"inf", "infinite", "unlimited", "unbounded"}: return None
    try: n = int(budget)
    except ValueError:
        print("[ERROR] DIVERGENCE_BUDGET is invalid (default=1000).")
        return 1000
    return None if n<0 else n

### Global caches and configuration options

# Contract cache ({var_name, storage_slot}) populated with build-info
LAYOUT_CACHE: dict[str, dict[str, int]] = {}

# Helpful ablation flags
DIVERGENCE_BUDGET = _parse_divergence_budget() # Cap forward-slice by CFG nodes (DivertScan §4.2.3 extension)
USER_CALLABLE_ALWAYS: Set[str] = { s.strip() for s in os.getenv("USER_CALLABLE_ALWAYS", "").split(",") if s.strip()}
USER_CALLABLE_DENY: Set[str] = { s.strip() for s in os.getenv("USER_CALLABLE_DENY", "").split(",") if s.strip()}
USER_CALLABLE_INCLUDE_ROLE_GATED: bool = os.getenv("USER_CALLABLE_INCLUDE_ROLE_GATED", "0") == "1" # 1: don't discard owner/role-gated entries
INIT_ONLY_FILTER = os.getenv("INIT_ONLY_FILTER", "1") == "1" # Remove benign findings from constructors/init
ADMIN_WRITES_BENIGN = os.getenv("ADMIN_WRITES_BENIGN", "1") == "1" # treats admin writes as benign with a user reader pair
ADMIN_ONLY = set()
COARSE_DEDUP = os.getenv("COARSE_DEDUP", "1") == "1" # (TODO: remove?)

### Value-influence sink test

# Sink behavior choices used in ablation testing:
#   "value"  -> value-influence sink (second iteration)
#   "samevar"-> same-var reread at branch/external-call (first iteration)
#   else     -> skip sink altogether (default)
SINK_TEST = (os.getenv("SINK_TEST") or "").strip().lower()

# get block id's reads and return if the var is in its reads
def block_reads_var(bid, sdg, var) -> bool:
    r = sdg.blocks.get(bid, {}).get("reads", set())
    if var in r: return True
    if isinstance(var, MappingSlotVar): return (var.base in r)
    return False

def _txt(s):
    try: return str(s).replace(" ", "").lower() # normalization
    except Exception: return ""

# Does the expression have that token?
def expr_uses_any(expr, tokens) -> bool:
    if not tokens: return False
    if expr is None: return False
    return any(t in _txt(expr) for t in tokens)

# Any external/internal call in this node has args/value derived from tokens
def node_ext_arg_uses_tokens(node, tokens) -> bool:
    for ir in getattr(node, "irs", []):
        irs = _txt(ir)
        if not irs: continue
        if any(t in irs for t in tokens): return True
    return False

# Return if node writes to storage and RHS of an assignment depends on our tokens
def node_storage_write_from_tokens(node, tokens) -> bool:
    # If the node writes no storage variables or slots, skip
    writes_storage = False
    if getattr(node, "variables_written", None): writes_storage = True

    # Scan IR to detect explicit writes and RHS dependency
    for ir in getattr(node, "irs", []):
        irs = _txt(ir)
        if not irs: continue

        is_write_like = ("sstore" in irs) \
            or ("storage" in irs and (":=" in irs or "=" in irs)) \
            or ("mapping" in irs and (":=" in irs or "=" in irs))
        writes_storage = writes_storage or is_write_like

        # Does the RHS contain a tracked token
        if any(t in irs for t in tokens) and (is_write_like and writes_storage): return True
    return False

# Within the node, grow the token set via local assignments: lv := rv
def update_aliases_in_block(node, tokens):
    if not tokens: return tokens

    new_tokens = set(tokens)
    for ir in getattr(node, "irs", []):
        try:
            if isinstance(ir, Assignment):
                lv_txt, rv_txt = _txt(getattr(ir, "lvalue", None)), _txt(getattr(ir, "rvalue", None))
                if lv_txt and rv_txt and any(t in rv_txt for t in tokens):
                    new_tokens.add(lv_txt)
        except Exception:
            irs = _txt(ir)
            if "=" in irs:
                lv, rv = irs.split("=", 1)
                lv, rv = lv.strip(), rv.strip()
                if any(t in rv for t in tokens) and lv: new_tokens.add(lv)
    return new_tokens

# A new sink heuristic: a read of 'var' is notable if, along some path without overwriting 'var', its value/copies influences:
# (a) control-flow at a branch predicate
# (b) arguments/eth value to an ext/internal call
# (c) RHS of a storage write to any storage var/slot
def value_influence_hits_sensitive_sink(var, start_bid, sdg, budget) -> bool:
    if budget == 0: return False

    # Same-node sink
    if is_critical_sink_bid(start_bid, sdg) and block_reads_var(start_bid, sdg, var): return True

    seen = {start_bid}
    q = deque([start_bid])
    steps = 0
    unlimited = (budget is None)
    while q and (unlimited or steps < budget):
        cur = q.popleft()
        steps += 1
        node = node_of(cur, sdg)

        # Branch predicate uses the variable
        if node and is_branch_node(node) and block_reads_var(cur, sdg, var):
            if reachable_without_overwrite(sdg, start_bid, cur, var):
                return True

        # Any call in the block and the block reads the variable
        if node and any(isinstance(ir, (HighLevelCall, InternalCall)) for ir in getattr(node, "irs", [])):
            if block_reads_var(cur, sdg, var) and reachable_without_overwrite(sdg, start_bid, cur, var):
                return True

        # Storage write in the block and the block reads the variable
        if node and (getattr(node, "variables_written", None) or any(getattr(ir, "lvalue", None) for ir in getattr(node, "irs", []))):
            if block_reads_var(cur, sdg, var) and reachable_without_overwrite(sdg, start_bid, cur, var):
                return True

        for nxt in sdg.blocks.get(cur, {}).get("succ", []):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return False

# sink-test scheduler
def hits_sink(var, read_bid, sdg) -> bool:
    if SINK_TEST == "value":
        return value_influence_hits_sensitive_sink(var, read_bid, sdg, DIVERGENCE_BUDGET)
    if SINK_TEST == "samevar":
        return forward_slice_hits_sink_from(var, read_bid, sdg, DIVERGENCE_BUDGET)
    return True

### Admin/role/timelock guards

# Inline guard detection
def has_inline_admin_guard(fn) -> bool:
    for n in getattr(fn, "nodes", []):
        if n.type not in branch_types: continue

        es = _txt(getattr(n, "expression", None))
        if not es: continue

        if ("msg.sender" in es and any(tok in es for tok in ("owner", "govern", "timelock", "guardian", "multisig", "admin"))) or \
           ("hasrole" in es or "onlyrole" in es) or \
           ("msg.sender" in es and ("role" in es or "isadmin" in es or "isowner" in es)):
            return True
    return False

# Admin if it has a popular admin name or has an inline admin guard
def is_admin_only(fn) -> bool:
    return True if any(getattr(m, "name", "").lower() in {"onlyowner", "onlyadmin", "onlyrole", "onlygovernance", "onlygov", "onlydao", "onlytimelock", "onlyguardian", "onlymultisig", "auth", "requiresauth", "checkowner"} for m in getattr(fn, "modifiers", []) or []) or has_inline_admin_guard(fn) else False

### Helpers for classifying nodes/shapes

# Resolve a block id to its node
def node_of(bid, sdg):
    fn = sdg.fn_lookup.get(bid[0])
    if fn is None: return None # missing
    for n in getattr(fn, "nodes", []):
        if n.node_id == bid[1]: return n
    return None # not found at all

def is_branch_node(node) -> bool: return (node.type in branch_types) # Check if node is a branching predicate defined by branch_types


# (DivertScan §4.2.3) Keep reads that reach external-call sites called "critical sinks." Call destination contamination could cause divergence
def is_external_call_node(node, sdg) -> bool:
    if node is None: return False # Node must exist

    # Heuristic for "critical sink": an external (cross-contract) call or dynamic low-level call
    fn = sdg.fn_lookup.get(node.function.full_name)
    if fn is None: return False
    for ir in getattr(node, "irs", []):
        if isinstance(ir, HighLevelCall):
            if ir.function is None:
                return True # dynamic or low-level call
            if getattr(ir.function, "contract_declarer", None) is not getattr(fn, "contract_declarer", None):
                return True # resolved callee belongs to a different contract
    return False

# (§4.2.3 Extension) A block is a critical sink if it's a branch predicate or an external call site.
def is_critical_sink_bid(bid, sdg) -> bool:
    node = node_of(bid, sdg)
    if node is None: return False # node must exist
    return is_branch_node(node) or is_external_call_node(node, sdg)

# (§4.2.3 Extension) Budgeted forward slice from a read to see if the same var is re-read at a sink
def forward_slice_hits_sink_from(var, start_bid, sdg, budget=DIVERGENCE_BUDGET) -> bool:
    if budget == 0: return False # NO traversal
    if start_bid in sdg.var_reads.get(var, set()) and is_critical_sink_bid(start_bid, sdg): return True

    # Bounded forward slice along CFG from the first read of a var at a start-bid
    reads_of_var = sdg.var_reads.get(var, set())
    seen: set[BasicBlock] = {start_bid}
    q, steps = deque([start_bid]), 0
    unlimited = (budget is None)
    while q and (unlimited or steps < budget):
        cur = q.popleft()
        steps += 1

        # If we reach a re-read, that is notable! Otherwise keep going
        if cur in reads_of_var and is_critical_sink_bid(cur, sdg):
            # Check for no overwrite along that part of CFG
            if reachable_without_overwrite(sdg, start_bid, cur, var): return True
        for nxt in sdg.blocks.get(cur, {}).get("succ", []):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return False

### Helpers for identifying init/constructor-only

def fn_entry_bid(fn):
    ep = getattr(fn, "entry_point", None)
    if ep is not None: return (fn.full_name, ep.node_id)

    # Pick node with no predicate or the first one available
    roots = [n for n in fn.nodes if not n.fathers]
    start = roots[0] if roots else (fn.nodes[0] if fn.nodes else None)
    if start is None: return None
    return (fn.full_name, start.node_id)

# Gets pre-latch tokens from `require` and `if` within the function
def latch_candidates_from_fn_guards(fn):
    toks = set()
    for n in fn.nodes:
        if n.type not in branch_types: continue
        es = _txt(getattr(n, "expression", None))
        if not es: continue

        # Bool case
        if "!" in es:
            tok = es.replace("!", "")
            if tok.isidentifier(): toks.add(tok)

        # Equality
        if "==" in es:
            left, right = es.split("==", 1)
            if left.isidentifier() and right in ("false", "0"): toks.add(left)

        # Bitmask
        if "&" in es and "==0" in es:
            left, _ = es.split("==0", 1)
            lhs = left.split("&", 1)[0]
            if lhs.isidentifier(): toks.add(lhs)

        # Versioning
        if "<" in es and "initialized" in es: toks.add("_initialized")

    # Name/modifier hint for common patterns
    nm = fn.name.lower()
    if ("init" in nm or "setup" in nm or "bootstrap" in nm) and any("initializer" in m.name.lower() or "reinitializer" in m.name.lower() for m in getattr(fn, "modifiers", [])):
        toks.add("initialized")
    return toks

# Determines if function contains a post-init guard referencing latch L in a way that implies the contract was already initialized
def fn_has_post_guard_for(fn, L) -> bool:
    for n in fn.nodes:
        if n.type not in branch_types: continue
        es = _txt(getattr(n, "expression", None))
        if not es: continue

        # Phase enums
        if L in {"initialized", "_initialized"} and ("phase==live" in es or "phase.live" in es): return True

        # Must mention the latch
        if L not in es: continue

        # Skip obvious pre-forms
        if f"!{L}" in es: continue
        if f"{L}==false" in es or f"{L}==0" in es: continue
        if L == "_initialized" and f"{L}<" in es: continue

        # Positive/post indications
        if f"{L}==true" in es or f"{L}==1" in es: return True
        if f"{L}>=" in es or f"{L}>" in es: return True
        if "&" in es and ("!=0" in es or "==0" not in es): return True

        return True
    return False

# Check if predicates are present
def preds_of(bid, sdg):
    info = sdg.blocks.get(bid, {})
    if "pred" in info and info["pred"] is not None: return list(info["pred"])
    
    # Derive preds from successor edges
    ps = []
    for other, inf in sdg.blocks.items():
        succs = inf.get("succ", set()) or []
        if bid in succs: ps.append(other)
    return ps

# We treat constructor writes as creation-phase, and check if the function is only reached from there
def is_creation_phase(v, w_bid, sdg) -> bool:
    fn = sdg.fn_lookup[w_bid[0]]
    if getattr(fn, "is_constructor", False): return True
    nm = fn.name.lower()
    if nm in {"bootstrap", "init","initialize","setup","set_up"} or any("initializer" in m.name.lower() for m in getattr(fn, "modifiers", [])):
        return True
    return False

# Accept if along any path from the write to the function return, there's an update moving L out of P_pre
def has_monotone_flip_write(L, w_bid, sdg) -> bool:
    # Over-approximate postdom region: all forward-reachable nodes in the function.
    fn, post, q = sdg.fn_lookup[w_bid[0]], set(), [w_bid]
    while q:
        cur = q.pop()
        for nxt in sdg.blocks[cur]["succ"]:
            if nxt not in post:
                post.add(nxt)
                q.append(nxt)
    
    L0 = L[0].lstrip("_").lower()
    for b in post:
        node = node_of(b, sdg)
        if node is None: continue
        for ir in getattr(node, "irs", []):
            if isinstance(ir, Assignment):
                lhs = str(getattr(ir, "lvalue", "")).lstrip("_").lower()
                rhs = str(getattr(ir, "rvalue", "")).lower()
                if lhs == L0:
                    # Monotone flips
                    if L[1] in ("bool", "eq") and ("true" in rhs or "ready" in rhs or "initialized" in rhs or "1" == rhs): return True
                    if L[1] == "mask_zero" and ("|" in rhs or "set" in rhs): return True
                    # Heuristic: Any write that looks like assignment to a non-zero/greater token
                    if L[1] == "version_lt" and (rhs not in ("0", "false")): return True
    return False

# Reject if we assign L back to a pre-init value anywhere in user-reachable code
def has_reset(L, sdg) -> bool:
    lname = L[0].lstrip("_").lower()
    for b in sdg.blocks:
        node = node_of(b, sdg)
        if node is None: continue
        for ir in getattr(node, "irs", []):
            if isinstance(ir, Assignment):
                lhs = str(getattr(ir, "lvalue", "")).lstrip("_").lower()
                rhs = str(getattr(ir, "rvalue", "")).replace(" ", "").lower()
                if lhs == lname and (rhs in ("false", "0", "phase.uninitialized") or ("&=~" in rhs)): return True
    return False

# For every public/ext entry reaching w_bid, ensure >=1 node on the path has a predicate mentioning L pre-initialization
def entry_paths_guarded(L, w_bid, sdg) -> bool:
    lname = L[0].lstrip("_").lower()

    # Walk backwards to entries
    seen, q, guarded_entries, entries = set(), [w_bid], set(), set()
    while q:
        cur = q.pop()
        fn = sdg.fn_lookup[cur[0]]
        if fn.visibility in ("public", "external"):
            entries.add(cur[0])

            # Check if one of cur's dominator(s) mentions L
            if any(lname in (str(getattr(n, "expression", "")).lower() or "") for n in fn.nodes):
                guarded_entries.add(cur[0])

        for pred in preds_of(cur, sdg):
            if pred not in seen:
                seen.add(pred)
                q.append(pred)
    return entries and entries.issubset(guarded_entries)

# Gets all L for which the func behaves like an initializer
def initializer_fn(fn, sdg):
    entry_bid = fn_entry_bid(fn)
    if entry_bid is None: return set()

    pre_latches = latch_candidates_from_fn_guards(fn)
    ok = set()
    for L in pre_latches:
        if has_monotone_flip_write((L, "eq", None), entry_bid, sdg) and not has_reset((L, "eq", None), sdg):
            ok.add(L)
    return ok

"""
(2) Accept if for every user-reachable path, find
  (a) a dominating guard that reads L and enforces it pre
  (b) a flip to move L out of pre that postdominates the write on that path,
  (c) no resets to bring L back into pre
"""
def passes_monotone_latch(v, w_bid, sdg) -> bool:
    # (a) Any predecessor chain nodes
    guard_nodes, work = {w_bid}, preds_of(w_bid, sdg)
    while work:
        b = work.pop()
        if b in guard_nodes: continue
        guard_nodes.add(b)
        work.extend(preds_of(b, sdg))

    # (b) Look for predicates of the form !x, x==c, (f & C)==0, _init < k
    latch_candidates = set()
    for n in guard_nodes:
        expr = getattr(n, "expression", None)
        if expr is None: continue
        es = str(expr).replace(" ", "").lower()

        # Bool
        if "!" in es:
            tok = es.replace("!", "")
            if tok.isidentifier(): latch_candidates.add((tok, "bool", None))
        
        # Equality and enum
        if "==" in es:
            left, right = es.split("==", 1)
            if left.isidentifier(): latch_candidates.add((left, "eq", right))
        
        # Bitmask
        if "&" in es and "==0" in es:
            left, _ = es.split("==0", 1)
            latch_candidates.add((left, "mask_zero", None))
        
        # Version
        if "<" in es and "_initialized" in es:
            latch_candidates.add(("_initialized", "version_lt", None))

    if not latch_candidates: return False

    # Check flip and no-reset for every candidate
    for L in latch_candidates:
        if has_monotone_flip_write(L, w_bid, sdg) and not has_reset(L, sdg):
            if entry_paths_guarded(L, w_bid, sdg): return True

    return False

# INIT_ONLY heuristics for filtering out any false positives that are found in initializers
def _init_only_vars(sdg) -> set:
    init_only = set()
    state_vars = [v for v in sdg.var_writes.keys() if not isinstance(v, (MappingSlotVar, MultiVarGroup, ExternalStateVar))]
    for v in state_vars:
        writes = sdg.var_writes.get(v, set())
        if not writes: continue
        if all(is_creation_phase(v, bid, sdg) or passes_monotone_latch(v, bid, sdg) for bid in writes): init_only.add(v)
    return init_only

### Variable id normalization for bucketing

# Returns key that supports every variable shape
def var_key(v):
    # Multi-var groups use their gid
    if isinstance(v, MultiVarGroup): return ("MVG", v.gid)

    # Mapping slots are keyed by the base mapping obj
    if isinstance(v, MappingSlotVar): return ("SV", id(v.base))

    return ("SV", id(v)) # Regular state variables

# (DivertScan's §4.2.1) Above-tx entry normalization that merges user-selected entry names
def normalize_entry_name(entry_name) -> str:
    if entry_name in {s.strip() for s in os.getenv("ATOMIC_GROUP", "").split(",") if s.strip()}:
        return "ATOMIC_GROUP"

    # Converts Contract.fn(arg,. ..) => Contract.fn
    if (os.getenv("MERGE_OVERLOADS", "0") == "1"):
        try:
            contract, rest = entry_name.split(".", 1)
            fn = rest.split("(", 1)[0].strip().strip("'\"")
            return f"{contract}.{fn}"
        except Exception:
            return entry_name
    return entry_name

### Precise storage slot resolution (0.9.2 has no storageLayout so i built this in using related works + solidity guide)

# Builds a name: slot map for a contract from Hardhat's artifacts/build-info/*
def slot_map(contract_name: str) -> dict[str, int]:
    canon = contract_name.split(":")[-1]
    if canon in LAYOUT_CACHE: return LAYOUT_CACHE[canon]

    merged = {}
    def merge_from_build_info(path: str):
        try: data = json.loads(pathlib.Path(path).read_text())
        except Exception: return
        contracts = (data.get("output") or {}).get("contracts")
        if not isinstance(contracts, dict): return
        for _, ctrs in contracts.items():
            ctr = ctrs.get(canon)
            if not isinstance(ctr, dict): continue
            layout = ctr.get("storageLayout") or {}
            for e in layout.get("storage", []) or []:
                lab, sl = (e.get("label") or "").lstrip("_"), e.get("slot")
                if lab and sl is not None:
                    try: merged.setdefault(lab, int(sl, 0))
                    except Exception: pass

    # Hardhat build-info
    for p in glob.glob("artifacts/build-info/*.json"): merge_from_build_info(p)

    # Foundry build-info
    for p in glob.glob("out/build-info/*.json"): merge_from_build_info(p)

    # Foundry per-contract artifacts (top-level storageLayout) area bit more difficult
    if not merged:
        for p in glob.glob("out/**/*.json", recursive=True):
            try: data = json.loads(pathlib.Path(p).read_text())
            except Exception: continue
            layout = data.get("storageLayout")
            if not isinstance(layout, dict): continue
            
            cn = data.get("contractName")
            if cn and cn != canon: continue
            for e in layout.get("storage", []) or []:
                lab = (e.get("label") or "").lstrip("_")
                sl  = e.get("slot")
                if lab and sl is not None:
                    try: merged.setdefault(lab, int(sl, 0))
                    except Exception: pass

    LAYOUT_CACHE[canon] = merged
    return merged

# Emit a finding to Slither's Output for later CLI use
def emit_finding(det, pattern, vars_hit, writers, readers, tx_list) -> Output:
    header = f"\n[{pattern}] " + ", ".join(vars_hit)
    lines  = [header, "  tx-set -> " + ", ".join(tx_list)]
    # Only the first few writer and reader sites are emitted, full detail in ISD_JSON_OUT
    for sig, _, f_path, l_no in writers[:2]: lines.append(f"\n • write\t{f_path}:{l_no}  ({sig})")
    for sig, _, f_path, l_no in readers[:2]: lines.append(f"\n • read\t{f_path}:{l_no}  ({sig})")
    return det.generate_result(lines) # Generate a valid result from the lines

def prettify(v): return None if getattr(v, "name", "").startswith("REF_") else getattr(v, "name", "") # Hides REF_*

"""
NOTE: NEW Added multi-variable grouping (branch groups and multi-return helpers).
Early works like DivertScan/SAILFISH were single-variable and could've used abstractions
"""
class MultiVarGroup:
    # Treat a set of related state vars as one logical variable so we can
    # 1. Detect multi-variable invariant violations
    # 2. Bucket and report them
    # 3. Propagate read and write sites into the pseudo for reachability and pair detection
    __slots__ = ("vars", "gid")
    def __init__(self, gid: int, vars_: tuple):
        self.gid, self.vars = gid, vars_
    
    @property
    def name(self): return "{" + ", ".join(sorted(filter(None, (prettify(x) for x in self.vars)))) + "}" # No REF_*

    # Hash the group and treat it as a statevar
    def __hash__(self): return hash(("BG", self.gid))

    # Check for equality between 2 grouping instances
    def __eq__(self, other): return isinstance(other, MultiVarGroup) and self.gid == other.gid

# Linearized base contracts acts differently on different versions and different frameworks
def _linearized_bases(c): return ( getattr(c, "linearized_base_contracts", None) or getattr(c, "_linearizedBaseContracts", None) or [] )

# Reconstruct slot's index by linearized base's order, excludes const/immutables but works for non-constant, non-immutable statevars
def legacy_slot_fallback(v):
    # Contract declaring v
    c = (getattr(v, "contract_declarer", None) or getattr(v, "contract", None))
    if not c: return None

    ordered = [] # walk the order
    for base in reversed(_linearized_bases(c)):
        ordered.extend(sv for sv in getattr(base, "state_variables", []) if not (getattr(sv, "is_constant", False) or getattr(sv, "is_immutable", False)))
    try:
        return ordered.index(v)
    except ValueError:
        return None

# Resolve storage slot numbers for regular state vars, mapping slots, and lastly legacy fallback
def slot_of(v):
    # NOTE: Some slither versions show storage_location in compilation
    loc = getattr(v, "_storage_location", {}) or getattr(v, "storage_location", {})
    if isinstance(loc, dict) and loc.get("slot") not in (None, "UNKNOWN"): return int(loc["slot"])

    # Build-info lookup (works for new Slither versions)
    c = (getattr(v, "contract_declarer", None) or getattr(v, "contract", None))
    tbl = slot_map(c.name if c else "")
    for label in (v.name, v.name.lstrip("_")):
        if (s := tbl.get(label)) is not None: return s

    return legacy_slot_fallback(v) # NO build-info! (this usually signals a bug so further research can fix these)

### SDG construction

def build_sdg(compilation_unit) -> SDG:
    sdg = SDG()

    # Visit every node of every function of every contract and add it to the SDG
    for contract in compilation_unit.contracts_derived:
        for fn in contract.functions_declared:
            # Populates blocks (CFG), var_reads/writes, fn_lookup, branch_groups, fn_returns, var_to_branchgroups, etc
            for node in fn.nodes: sdg.add_block(node)
    return sdg


### (DivertScan) §4.2.1 Entry reachability and user-callable heuristics

# How a function is considered user-callable
def is_user_callable(fn) -> bool:
    # Public or external and not a constructor or initializer
    if fn.visibility not in ("public", "external") or fn.is_constructor or fn.name.startswith("initialize"):
        return False

    # Treat common init-like names as non-user-callable
    nm =fn.name.lower()
    if nm in {"init", "initialize", "setup", "set_up", "bootstrap"} or nm.startswith("initialize"): return False

    # Outer name, then deny, approve, and filter role-gated
    outer = fn.full_name.split(".")[0]
    if outer in USER_CALLABLE_DENY: return False
    if outer in USER_CALLABLE_ALWAYS: return True
    if not USER_CALLABLE_INCLUDE_ROLE_GATED and is_admin_only(fn): return False
    return True

# Intersect each variable: blocks set with the reachable blocks and drop any empties
# Keeps read/write maps consistent after pruning for reachability
def filter_bid_map(bid_map: dict[StateVariable, set[BasicBlock]], keep):
    for v in list(bid_map.keys()):
        bid_map[v].intersection_update(keep)
        if not bid_map[v]: del bid_map[v]

# Helper to return (filename, first_line) for a (fn_name, node_id) block id
def src(bid, sdg):
    fn = sdg.fn_lookup[bid[0]]
    if fn is None: return "<unknown>", 0

    node = next((n for n in fn.nodes if n.node_id == bid[1]), None)
    if node is None or getattr(node, "source_mapping", None) is None: return "<unknown>", 0
    return node.source_mapping.filename.short, min(node.source_mapping.lines)

def fn_id(fn):
    # Return a uuid for a Slither func
    try:
        contract = fn.contract_declarer.name
    except AttributeError:
        contract = "<unknown>"
    raw_sig = getattr(fn, "signature", None)
    if not raw_sig:
        raw_sig = f"{fn.name}(" + ",".join(str(p.type) for p in fn.parameters) + ")"
    elif not isinstance(raw_sig, str):
        raw_sig = str(raw_sig)
    # recompute if needed
    pretty = f"{contract}.{raw_sig}"
    sel = getattr(fn, "selector", None)
    if sel is None: sel = int.from_bytes(keccak(text=raw_sig)[:4], "big")
    return pretty, hex(sel)

# Convert to u256 if you can, drop if can't
def _u256_or_none(s):
    try:
        return int(s, 0)
    except Exception:
        if isinstance(s, str) and s.startswith("0x"):
            try: return int(s, 16)
            except Exception: pass
    return None

"""
Pack variable metadata for JSON
• kind: state | external | mapping_slot | multi_var_group
• slot/base_slot/key where applicable
• branch_groups that mention the variable, useful for context
"""
def var_meta(v, sdg):
    vname_prettified = prettify(v.base if isinstance(v, MappingSlotVar) else v) or v.name

    # Handle multi-variable group
    if isinstance(v, MultiVarGroup):
        return {
            "name": vname_prettified,
            "kind": "multi_var_group",
            "members": [vv.name for vv in v.vars]
        }

    meta = {"name": vname_prettified}
    if isinstance(v, ExternalStateVar):
        meta["kind"] = "external"
    elif isinstance(v, MappingSlotVar):
        base = slot_of(v.base)
        meta.update({"kind": "mapping_slot", "base_slot": base, "key": v.key})
        k = _u256_or_none(v.key)
        if k is not None and base is not None:
            meta["slot"] = int.from_bytes(keccak(encode(["uint256","uint256"], [k, base])), "big")
        else: meta["slot_expr"] = v.key
    else:
        meta.update({"kind": "state", "slot": slot_of(v)})

    # Attach any branch-group id(s) that references this variable/base-mapping
    bg = sdg.var_to_branchgroups.get(v, set())
    if isinstance(v, MappingSlotVar): bg |= sdg.var_to_branchgroups.get(v.base, set())
    if bg: meta["branch_groups"] = sorted(bg)

    return meta

### Inconsistent state detector

class InconsistentState(AbstractDetector):
    """ Detect the inconsistent states """

    # Slither will launch the detector with slither . --detect inconsistent_state
    ARGUMENT = 'inconsistent_state'
    HELP = 'Inconsistent state detector'
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.HIGH

    WIKI = '..'
    WIKI_TITLE = 'Inconsistent state detector'
    WIKI_DESCRIPTION = 'Plugin testing'
    WIKI_EXPLOIT_SCENARIO = '..'
    WIKI_RECOMMENDATION = '..'

    """
    Detector pipeline
        (1) Compute storage layout for slot resolution
        (2) Build the SDG (CFG, def-use, and metadata)
        (3) Create pseudo-variables:
            (a) Branch groups with >= 2 variables
            (b) Functions returning multiple variables
        (4) Build call graph edges (intra and inter-contract)
        (5) Determine user-callable entries and keep only reachable blocks
        (6) Prune the variable read/write maps to reachable nodes
        (7) Enumerate stale_read_pairs() and optionally gate by a sink heuristic (SINK_TEST=value|samevar|none)
        (8) Detect any "shapes" of the finding (reentrancy, shared-callee)
        (9) Bucket by transaction set and variable
        (10)Canonicalize and deduplicate findings.
        (11)Emit Slither Output and machine-readable JSON for the exploit generator.
    """
    def _detect(self) -> List[Output]:
        # Storage layout checks
        for c in self.compilation_unit.contracts_derived:
            if hasattr(c, "set_storage_layout"): c.set_storage_layout()
            elif hasattr(c, "compute_storage_layout"): c.compute_storage_layout()

        # Deduplication key set across the findings
        seen: set[tuple] = set()

        # Set of all JSON-encoded findings and results
        json_findings, results = [], []

        # Builds the SDG
        sdg = build_sdg(self.compilation_unit)

        # Identify all admin-only functions
        global ADMIN_ONLY
        ADMIN_ONLY = { f.full_name for f in sdg.fn_lookup.values() if is_admin_only(f) }

        # Compute initialization-only variables before prune step
        pre_prune_init_only = set()
        init_latches_by_outer = defaultdict(set)
        all_init_latches: set[str] = set()
        if INIT_ONLY_FILTER: pre_prune_init_only = _init_only_vars(sdg)
        if INIT_ONLY_FILTER:
            for fn in sdg.fn_lookup.values():
                if fn.visibility not in ("public", "external"): continue
                outer = normalize_entry_name(fn.full_name.split(".")[0])
                Ls = initializer_fn(fn, sdg)
                if Ls:
                    init_latches_by_outer[outer].update(Ls)
                    all_init_latches |= Ls
        post_guarded_by_latch = defaultdict(set)
        if INIT_ONLY_FILTER and all_init_latches:
            for fn in sdg.fn_lookup.values():
                if fn.visibility not in ("public", "external"): continue
                outer = normalize_entry_name(fn.full_name.split(".")[0])
                for L in all_init_latches:
                    if fn_has_post_guard_for(fn, L): post_guarded_by_latch[L].add(outer)
        
        # Pseudovariables from branch-groups with >= 2 non-mapping-slot state variables
        bg_pseudos = {}
        for gid, members in sdg.branch_groups.items():
            concrete = tuple(sorted(
                (v for v in members if not isinstance(v, MappingSlotVar)),
                key=lambda x: x.name,
            ))

            # Skip the process if SV
            if len(concrete) < 2: continue

            pseudo = MultiVarGroup(gid, concrete)
            bg_pseudos[gid] = pseudo

            # Union read/write so it behaves like a variable within the SDG
            for v in concrete:
                sdg.var_reads[pseudo] |= sdg.var_reads.get(v, set())
                sdg.var_writes[pseudo] |= sdg.var_writes.get(v, set())

        # Map concrete variable to the pseudovariable(s) that it participates in
        var_to_pseudo = defaultdict(set)
        for pseudo in bg_pseudos.values():
            for v in pseudo.vars: var_to_pseudo[v].add(pseudo)

        # - Include BOTH mapping slots and their base mapping in the group, so co-use like
        #   balances[user] together with balances (base) doesn't get collapsed.
        # - Union reads/writes from BOTH the slot and the base into the pseudo.
        for fn, ret_vars in sdg.fn_returns.items():

            # Collect slots and bases
            slots_and_bases = set()
            for rv in ret_vars:
                if isinstance(rv, MappingSlotVar):
                    # Concrete slot (e.g., A[a]), then base mapping (A)
                    slots_and_bases.add(rv)
                    slots_and_bases.add(rv.base)
                else:
                    # Just the concrete slot (e.g. A[a])
                    slots_and_bases.add(rv)

            if len(slots_and_bases) < 2: continue # singletons are skipped

            # Human-facing members should be the concrete state vars
            members = tuple(sorted(
                { (x.base if isinstance(x, MappingSlotVar) else x) for x in slots_and_bases },
                key=lambda x: x.name
            ))

            # prevent grouping 1 into an MVG
            if len(members) < 2: continue

            gid = id(fn)
            pseudo = MultiVarGroup(gid, members)
            bg_pseudos[gid] = pseudo

            # Union r/w from both slots and bases; base->pseudo bucket mapping
            for v in slots_and_bases:
                sdg.var_reads[pseudo] |= sdg.var_reads.get(v, set())
                sdg.var_writes[pseudo] |= sdg.var_writes.get(v, set())
                var_to_pseudo[(v.base if isinstance(v, MappingSlotVar) else v)].add(pseudo)

        # # Flag to show the pseudovariables in order to better understand grouping structure
        # if os.getenv("DEBUG_PSEUDOVARS"):
        #     for pseudo in bg_pseudos.values(): print("[bg] pseudo", pseudo.gid, "->", pseudo.name)

        # Build call-graph edges
        call_edges_intra: dict[str, set[str]] = defaultdict(set) # NOTE: Currently unused, but left for future work
        call_edges_any: dict[str, set[str]] = defaultdict(set)
        for fn in sdg.fn_lookup.values():
            for n in fn.nodes:
                for ir in getattr(n, "irs", []):
                    if not isinstance(ir, (HighLevelCall, InternalCall)): continue
                    callee = ir.function
                    if callee is None: continue  # Ignore dynamic/low-level calls
                    caller_ctr, callee_ctr = getattr(fn, "contract_declarer", None), getattr(callee, "contract_declarer", None)
                    call_edges_any[fn.full_name].add(callee.full_name)
                    if caller_ctr is callee_ctr: call_edges_intra[fn.full_name].add(callee.full_name)

        # (DivertScan §4.2.1) Restrict to public or external entries deemed user-callable
        public_entries: set[BasicBlock] = { bid for bid in sdg.blocks if (fn := sdg.fn_lookup.get(bid[0])) and is_user_callable(fn) }

        # Worklist reachability from public_entries to track the entry owner of each block
        keep: set[BasicBlock] = set()
        entry_of: dict[BasicBlock, str] = {}
        stack: list[BasicBlock] = list(public_entries)
        for bid in public_entries:
            # (DivertScan Extensions §4.2.1) (above-tx level) Supports merging user-named entries into one atomic unit.
            entry_of[bid] = normalize_entry_name(bid[0]) # VU: [FIXED] Keeps function-level identity which is normalized
        while stack:
            cur = stack.pop()
            if cur in keep: continue
            keep.add(cur)
            
            # Every kept block inherits the outer public entry that reaches it in the same tx
            for nxt in sdg.blocks[cur]["succ"]:
                if nxt not in entry_of: entry_of[nxt] = entry_of[cur]
                stack.append(nxt)

        # Prune unreachable blocks and synchronize read/write maps
        sdg.blocks = {b: info for b, info in sdg.blocks.items() if b in keep}
        filter_bid_map(sdg.var_reads, keep)
        filter_bid_map(sdg.var_writes, keep)

        # Bucket findings by tx-set: var: pairs with shape tags
        buckets = defaultdict(lambda: defaultdict(list)) # {tx_id: {var: [(w_bid,r_bid,pattern,srcs...)]}}
        shapes_by_key = defaultdict(lambda: {"shared_callee": False, "reentrant": False})

        # Enumerate raw pairs by SDG def-use
        for w_bid, r_bid, var, pattern in stale_read_pairs(sdg):
            # Skip when the writer is admin-only but the reader is a normal user entry
            if ADMIN_WRITES_BENIGN:
                w_full, r_full = sdg.fn_lookup[w_bid[0]].full_name, sdg.fn_lookup[r_bid[0]].full_name
                if (w_full in ADMIN_ONLY) and (r_full not in ADMIN_ONLY): continue

            # Skip pairs where the written var is proven init-only
            if INIT_ONLY_FILTER:
                if getattr(var, "base", var) in pre_prune_init_only: continue

            """
            (DivertScan §4.2.1) (transaction-level) Enumerates all pairs of public entries by bucketing on tx_id.
            (DivertScan §4.2.2) Pairs are implicitly public-only due to reachability pruning.
            """

            # Transaction identity is the set of outer entry names that reach write/read
            tx_id = frozenset({entry_of[w_bid], entry_of[r_bid]})
            outer_w, outer_r = entry_of[w_bid], entry_of[r_bid]

            # Sink check is gated by the env variable set
            if not hits_sink(var, r_bid, sdg): continue

            # VU: [FIXED] Drop benign findings if runtime is post-gated by the same latch that init flips
            if INIT_ONLY_FILTER:
                init_Ls = init_latches_by_outer.get(outer_w, set())
                if init_Ls and any(outer_r in post_guarded_by_latch.get(L, set()) for L in init_Ls): continue

            # (DivertScan §4.2.1) (function-level) Mark reachable reentrant pairs when outer entries mutually call
            reentrant = False
            w_full, r_full = sdg.fn_lookup[w_bid[0]].full_name, sdg.fn_lookup[r_bid[0]].full_name
            if outer_w != outer_r:
                if (r_full in call_edges_any.get(w_full, set())) or (w_full in call_edges_any.get(r_full, set())):
                    reentrant = True

                    # these labels can help to triage downstream?
                    if pattern == "stale_read": pattern = "reentrant_stale_read"
                    elif pattern == "destructive_write": pattern = "reentrant_destructive_write"

            # Shared-callee: if both outer entries call at least one same callee
            shared_callee = False
            w_callees, r_callees = call_edges_any.get(w_full, set()), call_edges_any.get(r_full, set())
            if w_callees and r_callees and (w_callees & r_callees): shared_callee = True

            # Record aggregated shapes by their (tx_id, var_key)
            if shared_callee:
                shapes_by_key[(tx_id, var_key(var))]["shared_callee"] = True
            if reentrant:
                shapes_by_key[(tx_id, var_key(var))]["reentrant"] = True

            # Bucketing
            w_file, w_line = src(w_bid, sdg)
            r_file, r_line = src(r_bid, sdg)
            buckets[tx_id][var].append((w_bid, r_bid, pattern, w_file, w_line, r_file, r_line))

            base_v = var.base if isinstance(var, MappingSlotVar) else var
            for pseudo in var_to_pseudo.get(base_v, []):
                buckets[tx_id][pseudo].append((w_bid, r_bid, pattern, w_file, w_line, r_file, r_line))

        # Emit canonicalized buckets to Slither Output/JSON
        for tx_id, var_map in buckets.items():
            # Classify bucket type
            vars_here = list(var_map.keys())
            contracts = {
                getattr(v, "base", v).contract_declarer if hasattr(v, "base")
                else getattr(v, "contract_declarer", None) for v in vars_here
            }
            contracts.discard(None)

            # (1) Standard single-variable inconsistent state finding
            # (2) Multiple variables declared in same contract
            # (3) Multiple variables declared in different contracts
            if len(vars_here) == 1 and not isinstance(vars_here[0], MultiVarGroup):
                bucket_class = "single_var_cross_tx"
            elif len(contracts) == 1:
                bucket_class = "multi_var_intra_contract"
            else:
                bucket_class = "multi_var_cross_contract"

            tx_list = sorted(tx_id)

            # Collect a few example sites/op-level patterns for the bucket
            writers, readers, op_patterns = [], [], set()
            for v, pairs in var_map.items():
                for w_bid, r_bid, op_pat, w_file, w_line, r_file, r_line in pairs[:3]:
                    w_sig, w_sel = fn_id(sdg.fn_lookup[w_bid[0]])
                    r_sig, r_sel = fn_id(sdg.fn_lookup[r_bid[0]])
                    writers.append((w_sig, w_sel, w_file, w_line))
                    readers.append((r_sig, r_sel, r_file, r_line))
                    op_patterns.add(op_pat)

            # Aggregate shape tags across variables
            agg_shape = {
                "shared_callee": any(shapes_by_key[(tx_id, var_key(v))]["shared_callee"] for v in vars_here),
                "reentrant": any(shapes_by_key[(tx_id, var_key(v))]["reentrant"] for v in vars_here),
            }
            per_var_shapes = [{ "var": var_meta(v, sdg), "shape": shapes_by_key[(tx_id, var_key(v))] } for v in vars_here]

            """
            We canonicalize and deduplicate the pattern, variables, transaction set, writers, and readers.
            This ensures a stable JSON output.
            """
            writers, readers = list({t for t in writers}), list({t for t in readers})

            if COARSE_DEDUP:
                key = (
                    bucket_class,
                    tuple(sorted([var_key(v) for v in vars_here])),  # shape, not site
                    tuple(tx_list),
                    tuple(sorted(op_patterns)),
                    agg_shape["reentrant"],
                    agg_shape["shared_callee"]
                )
            else:
                key = (
                    bucket_class,
                    tuple(sorted([v.name for v in vars_here])),
                    tuple(tx_list),
                    frozenset(writers),
                    frozenset(readers),
                )
            if key in seen: continue
            seen.add(key)

            # JSON finding
            json_findings.append({
                "pattern": bucket_class,
                "vars": [var_meta(v, sdg) for v in vars_here],
                "tx_set": tx_list,
                "writers": [{"sig": sig, "selector": sel, "file": f, "line": l} for sig, sel, f, l in writers],
                "readers": [{"sig": sig, "selector": sel, "file": f, "line": l} for sig, sel, f, l in readers],
                "op_patterns": sorted(op_patterns), # per-pair shapes seen inside the bucket
                "shape": agg_shape, # aggregated across variables
                "shape_by_var": per_var_shapes, # precise per variable
            })

            # Slither Output objs
            results.append(emit_finding(self, bucket_class, [v.name for v in vars_here], writers, readers, tx_list))

        # Return machine-readable JSON for a future dynamic exploit generator
        if os.getenv("ISD_JSON_OUT"):
            with open(os.getenv("ISD_JSON_OUT"), "w") as fh: json.dump(json_findings, fh, indent=2)

        return results