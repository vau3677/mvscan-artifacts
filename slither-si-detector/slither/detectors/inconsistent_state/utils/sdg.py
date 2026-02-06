"""
sdg.py
Implementation of our SDG for MV-SCAN

Author: Vladislav Usatii (vau3677@rit.edu)
"""
import os, re
from typing import Dict, Set, Tuple
from collections import defaultdict, deque
from slither.core.cfg.node import Node
from slither.core.variables.state_variable import StateVariable
from slither.core.cfg.node import NodeType
from slither.slithir.operations import HighLevelCall, InternalCall, OperationWithLValue, Assignment

from .alias import ALIAS_REG

# Only promote mapping base into the group when explicitly enabled (for ablation testing)
PROMOTE_MAPPING_BASE = os.getenv("PROMOTE_MAPPING_BASE", "0") == "1"

# external r/w classification tables
EXT_READS  = {"balanceof", "balanceof(address)", "totalsupply", "lastbalance"}
EXT_WRITES = {"transfer", "transferfrom", "mint", "burn", "sync"}

# storage var mapped to public getter selector
STORAGE_TO_SELECTOR = {
    "_lastBalance": "lastbalance",
    "balances":     "balanceof",
    "_balances":    "balanceof",
    "balanceOf":    "balanceof",
}

### Ablation toggles

# Toggle that implements DivertScan's §4.2.3 P.4
NOOP_WRITE_FILTER = os.getenv("NOOP_WRITE_FILTER", "1") == "1"

# Require same mapping-slot key for r/w pairs when both sides use slots of the same base mapping
REQUIRE_SAME_SLOT_KEY = os.getenv("REQUIRE_SAME_SLOT_KEY", "1") == "1"

### Helpers for mapping-key agreement

# Return { base_map_sv -> set(keys) } seen at a block for r/w
def slot_keys_at(sdg, bid, kind: str) -> dict:
    out = defaultdict(set)
    for v in sdg.blocks[bid][kind]:
        if isinstance(v, MappingSlotVar): out[v.base].add(v.key)
    return out

### Helpers to implement no-op from DivertScan

# Helper to normalize variable text
def norm_txt(s) -> str:
    t = re.sub(r"\baddress\((.+?)\)", r"\1", (s or "").replace("this.", ""))
    return t.replace(" ", "").lower()

# Canon a key expression
def canon_key(k) -> str: return norm_txt(str(k))

def var_key_txt(v) -> str:
    t = norm_txt(str(getattr(v, "name", v)))
    return t if t and t != "none" else norm_txt(str(v))

# Collect simple SSA-style defs in this node
def build_defs_map(node):
    defs = {}
    for ir in getattr(node, "irs", []):
        if isinstance(ir, Assignment):
            lv, rv = norm_txt(str(getattr(ir, "lvalue", ""))), norm_txt(str(getattr(ir, "rvalue", "")))
            if lv: defs.setdefault(lv, rv)
    return defs

# Follow <= max_hops aliases inside the same node
def resolve_alias(txt, defs, max_hops=3) -> str:
    seen, cur = set(), txt
    for _ in range(max_hops):
        if cur in seen: break
        seen.add(cur)
        nxt = defs.get(cur)
        if not nxt: break
        cur = nxt
    return cur

# (DivertScan §4.2.3) Drop a pair w, r when the write sets v:=v or mapping slots like balances[a]:=balances[a].
def is_self_copy_write(v, node) -> bool:
    # Don't attempt on externals
    if type(v).__name__ == "ExternalStateVar": return False

    x, defs = var_key_txt(v), build_defs_map(node)
    found_write = False
    for ir in getattr(node, "irs", []):
        if not isinstance(ir, Assignment): continue
        lv, rv = norm_txt(str(getattr(ir, "lvalue", ""))), norm_txt(str(getattr(ir, "rvalue", "")))
        if lv != x: continue
        found_write = True
        if rv == x: continue
        if resolve_alias(rv, defs) == x: continue
        return False
    return found_write

# abstracts 1 concrete storage slot of a mapping/array (e.g. balances[addr] or prices[id])
class MappingSlotVar:
    __slots__ = ("base", "key")
    def __init__(self, base: StateVariable, key: str):
        self.base = base # StateVariable
        self.key = key # canonical key expression as a string

    def __hash__(self):
        return hash((self.base, self.key))

    def __eq__(self, other):
        return isinstance(other, MappingSlotVar) and self.base == other.base and self.key == other.key

    @property
    def name(self):
        return f"{self.base.name}[{self.key}]"

    def __str__(self):
        return self.name # @property
    __repr__ = __str__

# Return contract id
def contract_id(contract) -> str:
    return getattr(contract, "canonical_name", contract.name)

# Strip an outer entry
def outer_entry(full_name: str) -> str: return full_name # VU: [FIXED] Keep the function-level identity

# Detect constants or immutables
def is_const(v: StateVariable) -> bool: return getattr(v, "is_constant", False) or getattr(v, "is_immutable", False)

# Detect 32-byte role constants (e.g. DEFAULT_ADMIN)
def is_role_bytes32(v: StateVariable) -> bool: return v.type == "bytes32" and v.name.endswith("_ROLE")

# Detect if function can't write to storage
def is_view_only(fn) -> bool:
    if hasattr(fn, "state_mutability"): return fn.state_mutability in ("view", "pure") # >=0.9.3
    return getattr(fn, "is_view", False) or getattr(fn, "is_pure", False) # <=0.9.2

# Detect if any non-[view/pure] func in CU calls fn
def called_from_stateful(fn, sdg):
    for f in sdg.fn_lookup.values():
        if is_view_only(f): continue
        for n in f.nodes:
            for ir in n.irs:
                if isinstance(ir, (HighLevelCall, InternalCall)) and ir.function == fn: return True
    return False

# Treat any obj with variable_left/variable_right as a slot
def is_index_var(obj) -> bool:
    return hasattr(obj, "variable_left") and hasattr(obj, "variable_right")

# Makes a new mapping slot
def mk_slot(base, key) -> MappingSlotVar:
    # print(f"[mk_slot] {base.name}[{key}] id={id(base)}") # [DEBUG] keys should differ for msg.sender vs another address
    return MappingSlotVar(base, canon_key(key))

# Substitute callee param names with caller args for mapping-slot keys
def _subst_returns_with_args(callee, ir, expr_vars):
    sub_reads, args, params = set(), list(getattr(ir, "arguments", []) or []), list(getattr(callee, "parameters", []) or [])
    subst = {}
    for i, p in enumerate(params):
        if i < len(args):
            pname = getattr(p, "name", f"arg{i}")
            subst[pname] = canon_key(args[i])
    for rv in expr_vars:
        if isinstance(rv, MappingSlotVar):
            k = subst.get(rv.key, rv.key)
            sub_reads.add(MappingSlotVar(rv.base, k))
        else:
            sub_reads.add(rv)
    return sub_reads

# wrapper so we can store <external selector> in the SDG and still hash/compare it like a real StateVariable
class ExternalStateVar:
    __slots__ = ("selector", "addr")
    def __init__(self, selector: str, addr: str | None):
        self.selector = selector.lower()
        self.addr = (addr or "unknown").lower()

    @property
    def name(self) -> str: # for debugging / prints
        return f"{self.addr}.{self.selector}"

    def __hash__(self):
        return hash((self.selector, self.addr))

    def __eq__(self, other):
        return (isinstance(other, ExternalStateVar)
            and self.selector == other.selector
            and self.addr     == other.addr)

    def __str__(self):
        return f"EXT::{self.addr}::{self.selector}"
    __repr__ = __str__

# Minimal SDG where blocks[bid] maps to r/w/succ and var_reads/writes map to blocks where bid is read/write
BasicBlock = Tuple[str, int]
class SDG:
    def __init__(self):
        self.blocks: Dict[BasicBlock, Dict[str, Set]] = {}
        self.var_reads: Dict[StateVariable, Set[BasicBlock]] = defaultdict(set)
        self.var_writes: Dict[StateVariable, Set[BasicBlock]] = defaultdict(set)
        self.fn_lookup = {} # full_name -> Function
        self.branch_groups: Dict[int, Set] = defaultdict(set)
        self.var_to_branchgroups: Dict[object, Set[int]] = defaultdict(set)
        self.fn_returns = {} # Function -> Set[Var]

    # Populate the SDG with one basic block & its inter-procedural edges
    def add_block(self, node: Node):
        block_id: BasicBlock = (node.function.full_name, node.node_id)

        # Processed these already
        if block_id in self.blocks: return

        # Gather storage reads and writes
        reads:  Set[StateVariable | MappingSlotVar | ExternalStateVar] = set()
        writes: Set[StateVariable | MappingSlotVar | ExternalStateVar] = set()

        # Adds all reads
        for v in node.variables_read:
            if isinstance(v, StateVariable):
                reads.add(v)
            elif is_index_var(v): # Mapping/array load
                reads.add(mk_slot(v.variable_left, v.variable_right))
        # Adds all writes
        for v in node.variables_written:
            if isinstance(v, StateVariable):
                writes.add(v)
            elif is_index_var(v): # mapping/array store
                writes.add(mk_slot(v.variable_left, v.variable_right))
        # Extra IR scan for lvalues that slither misses
        for ir in node.irs:
            if isinstance(ir, OperationWithLValue):
                lv = ir.lvalue
                if is_index_var(lv): # slot write
                    writes.add(mk_slot(lv.variable_left, lv.variable_right))

        # Only freshly-collected writes
        for w in list(writes):
            if not isinstance(w, StateVariable): continue
            sel = STORAGE_TO_SELECTOR.get(w.name)
            if not sel: continue # none to alias
            token_addr = contract_id(node.function.contract_declarer)
            alias_var = ALIAS_REG.get_or_create(token_addr, sel, node.function.full_name, lambda: ExternalStateVar(sel, token_addr))
            writes.add(alias_var)

        # Summarize simple view/pure returns
        fn = node.function

        # diagnostic debug for fn_returns [this finding actually helped us reach our milestone of MV-SI detection!]
        # if fn.name == "stakedAndActionLockedBalanceOf":
        #     print("[diag ]", fn.full_name, "view?", _is_view_only(fn), "internal_calls:", len(getattr(fn, "internal_calls", [])))

        if fn not in self.fn_returns:
            # Consider it summarizable iff it writes no STORAGE (locals allowed)
            writes_storage = False
            for n_ in fn.nodes:
                # Check for any explicit storage variable write
                if any(isinstance(vv, StateVariable) for vv in n_.variables_written):
                    writes_storage = True
                    break
                # IR lvalue catch for mapping/array writes
                for ir_ in n_.irs:
                    if isinstance(ir_, OperationWithLValue) and is_index_var(ir_.lvalue):
                        writes_storage = True
                        break
                if writes_storage: break

            if not writes_storage:
                ret_nodes = [n for n in fn.nodes if n.type == NodeType.RETURN]
                if ret_nodes:
                    expr_vars = set()
                    for ret in ret_nodes:
                        # Plain state vars read
                        expr_vars |= {v for v in ret.variables_read if isinstance(v, StateVariable)}
                        
                        # Mapping/array slots
                        expr_vars |= {
                            mk_slot(ir.variable_left, ir.variable_right)
                            for ir in ret.irs
                            if is_index_var(ir)
                        }
                    if len(expr_vars) >= 2: self.fn_returns[fn] = expr_vars
                    #print(f"[summary] {fn.full_name} -> {', '.join(v.name for v in expr_vars)}") # [DEBUG] shows us summaries of |fn| >= 2

        # Tags conditionals that mix >=2 variables
        if node.type in branch_types:
            cond_vars  = set()

            # Plain state variables already seen as reads
            cond_vars |= {v for v in node.variables_read if isinstance(v, StateVariable)}

            # Mapping/array slots already seen as reads
            cond_vars |= {mk_slot(v.variable_left, v.variable_right) for v in node.variables_read if is_index_var(v)}

            # External GSV wrappers already seen as reads
            cond_vars |= {rv for rv in reads if isinstance(rv, ExternalStateVar)}

            # Inline summaries of view and pure calls
            for ir in node.irs:
                if isinstance(ir, (HighLevelCall, InternalCall)) and ir.function in self.fn_returns:
                    cond_vars |= self.fn_returns[ir.function]

                    # Mark summarized return vars as reads at this node, so sinks see the reread
                    for vv in self.fn_returns[ir.function]: reads.add(vv)

                    # print(f"[call  ] {fn.full_name}:{node.node_id} -> uses {ir.function.full_name}") # [DEBUG] shows us all calls

                # 0.9.2 fallback
                elif isinstance(ir, (HighLevelCall, InternalCall)) and ir.function is None:
                    # Resolves by text name
                    callee_name = str(ir.function_name) # e.g. "stakedAndActionLockedBalanceOf" in Bug 112
                    callee_fn   = next((f for f in self.fn_lookup.values() if f.name == callee_name), None)
                    if callee_fn and callee_fn in self.fn_returns:
                        cond_vars |= self.fn_returns[callee_fn]
                        for vv in self.fn_returns[callee_fn]: reads.add(vv)
                        print(f"[call? ] {fn.full_name}:{node.node_id} -> fallback uses {callee_fn.full_name}")

            # Show the raw variables seen in this conditional
            if cond_vars:
                fmt = ", ".join(v.name for v in cond_vars)

                # [DEBUG] shows conditional variables
                #print(f"[cond  ] {fn.full_name}:{node.source_mapping.lines[0]} -> {fmt}")

            # We care iff 2 or more variables involved
            if len(cond_vars) >= 2:
                # We use a cheap unique gid to classify
                gid = id(node)
                for cv in cond_vars:
                    self.branch_groups[gid].add(cv)
                    self.var_to_branchgroups[cv].add(gid)

                    # Additionally tag the mapping base so all keys share the group
                    # print(f"[PROMOTE_MAPPING_BASE] Set to {PROMOTE_MAPPING_BASE}.")
                    if isinstance(cv, MappingSlotVar) and PROMOTE_MAPPING_BASE:
                        base = cv.base
                        self.branch_groups[gid].add(base)
                        self.var_to_branchgroups[base].add(gid)

                # [DEBUG] shows groups for branching
                #print(f"[group] {gid} <- {', '.join(v.name for v in self.branch_groups[gid])}")

        # ERC-20 balance mapping writes should alias EXT::balanceof
        for ir in node.irs:
            if not isinstance(ir, OperationWithLValue): continue
            if getattr(ir.lvalue, "name", "") in ("balances", "_balances", "balanceOf"):
                token_addr = contract_id(node.function.contract_declarer)
                writes.add(ExternalStateVar("balanceof", token_addr))

        # Does contract expose a public getter?
        if any(isinstance(v, StateVariable) and v.name == "_lastBalance" for v in writes):
            if any(f.name == "lastBalance" and f.visibility == "public" for f in node.function.contract_declarer.functions_declared):
                token_addr = contract_id(node.function.contract_declarer)
                writes.add(ExternalStateVar("lastbalance", token_addr))

        # Intra-procedural successors
        succ: Set[BasicBlock] = {(node.function.full_name, s.node_id) for s in node.sons}

        # Handle every call IR in this block
        for ir in node.irs:

            # Drop any IR that isn't a high-level or internal call
            if not isinstance(ir, (HighLevelCall, InternalCall)): continue

            # Call-graph edges could be Function, None, or Variable
            callee = ir.function
            if getattr(callee, "entry_point", None) is not None:
                entry_bid = (callee.full_name, callee.entry_point.node_id)
                succ.add(entry_bid)

                # Ensure entry node exists
                if entry_bid not in self.blocks:
                    self.blocks[entry_bid] = {
                        "reads": set(),
                        "writes": set(),
                        "succ": set()
                    }
                self.fn_lookup.setdefault(callee.full_name, callee)

                # Every callee returns with additional leaf fall-backs
                exit_nodes = [n for n in callee.nodes if n.type == NodeType.RETURN]
                if not exit_nodes: exit_nodes = [n for n in callee.nodes if not n.sons]
                for exit_node in exit_nodes:
                    exit_bid = (callee.full_name, exit_node.node_id)
                    if exit_bid not in self.blocks:
                        self.blocks[exit_bid] = {
                            "reads": set(),
                            "writes": set(),
                            "succ": set()
                        }
                    self.blocks[exit_bid]["succ"].add(block_id)

            # Summarize view/pure returns into reads at the call site
            if callee in self.fn_returns:
                reads |= _subst_returns_with_args(callee, ir, self.fn_returns[callee])
            elif callee is None:
                callee_name = str(ir.function_name)
                callee_fn   = next((f for f in self.fn_lookup.values() if f.name == callee_name), None)
                if callee_fn and callee_fn in self.fn_returns:
                    reads |= _subst_returns_with_args(callee_fn, ir, self.fn_returns[callee_fn])

            # External-state abstraction
            callee_sel = str(ir.function_name).split('(')[0].lower()
            if callee_sel in EXT_READS or callee_sel in EXT_WRITES:
                # Best-effort stable address string
                dest = getattr(ir, "destination", None)
                addr = getattr(dest, "canonical_name", getattr(dest, "name", None))
                caller_fn = node.function.full_name

                # Obtain 1 canonical wrapper for this call-site
                def mk_wrapper():
                    return ExternalStateVar(callee_sel, addr)

                ext_var = ALIAS_REG.get_or_create(addr, callee_sel, node.function.full_name, mk_wrapper)
                if callee_sel in EXT_READS: reads.add(ext_var)
                if callee_sel in EXT_WRITES: writes.add(ext_var)

        # Commits the caller block and updates
        self.blocks[block_id] = {"reads": reads, "writes": writes, "succ": succ}
        self.fn_lookup[node.function.full_name] = node.function
        for v in reads: self.var_reads[v].add(block_id)
        for v in writes: self.var_writes[v].add(block_id)

### SDG helpers

branch_types = {NodeType.IF}
for t in ("REQUIRE", "ASSERT", "REVERT"):
    if hasattr(NodeType, t): branch_types.add(getattr(NodeType, t))

# Node lookup
def node_by_id(fn, node_id):
    for n in fn.nodes:
        if n.node_id == node_id: return n
    return None

def var_used(node, v):
    return v in getattr(node, "state_variables_read", []) or v in getattr(node, "variables_read", [])

# A call that invokes require or assert
def is_require_like(node):
    try:
        return "require(" in str(node.expression) or "assert(" in str(node.expression)
    except Exception:
        return False

# Returns iff dst_bid is reachable from src_bid without passing through a block that writes `v` (other than the src)
def reachable_without_overwrite(sdg: SDG, src_bid, dst_bid, v) -> bool:
    # If the read happens in a block that is itself a branch/ext-call sink
    if src_bid == dst_bid: return True

    seen, q = set([src_bid]), deque([src_bid])
    while q:
        cur = q.popleft()
        for nxt in sdg.blocks[cur]["succ"]:
            # Reached target
            if nxt == dst_bid: return True

            # Already visited
            if nxt in seen: continue

            # Overwrote v, continue
            if v in sdg.blocks[nxt]["writes"]: continue

            seen.add(nxt)
            q.append(nxt)
    return False

# Does a read affect state
def read_affects_state(sdg, read_bid, v):
    fn_name, node_id = read_bid
    fn = sdg.fn_lookup[fn_name]
    start = node_by_id(fn, node_id)
    if start is None: return False

    q, seen = deque([start]), {start}
    while q:
        cur = q.popleft()
        # Control flow divergence
        if cur is not start and var_used(cur, v): return True

        ## Data flow divergence (state write)

        # Any state write after the read
        if cur.variables_written: return True

        # Stop once v is overwritten
        if cur is not start and v in cur.variables_written: continue
        for s in cur.sons:
            if s not in seen:
                seen.add(s)
                q.append(s)
    return False

# Yields tuples (write, read, sv, 'stale_read'/'destructive_write')
def stale_read_pairs(sdg: SDG):
    for v, writes in sdg.var_writes.items():
        # Strip the constructor/initializer writer blocks
        writes = {w for w in writes if not (sdg.fn_lookup[w[0]].is_constructor \
            or sdg.fn_lookup[w[0]].name.startswith("initialize"))}
        if not writes: continue

        # Tells us if detector sees r/w for the balance mapping
        # if v.name.startswith("balances"): print(f"[sr_scan] scanning var {v.name} : {len(writes)} writes, {len(sdg.var_reads.get(v,[]))} reads")

        # Skip constants, immutables, role-ids, and None
        if v is None or (isinstance(v, StateVariable) and (is_const(v) or is_role_bytes32(v))): continue

        reads = sdg.var_reads.get(v, set())
        if not reads: continue # no reads

        if all(sdg.fn_lookup[w[0]].is_constructor or \
            sdg.fn_lookup[w[0]].name.startswith("initialize") for w in writes): continue

        yielded = set() # (write_fn, read_fn, v)
        for w_bid in writes:
            for r_bid in reads:
                # Debug print pairs
                # if isinstance(v, MappingSlotVar):
                #     print(f"[pair?] {v.name} BG slot={bool(sdg.var_to_branchgroups.get(v))} BG base={bool(sdg.var_to_branchgroups.get(v.base))}")

                key = (w_bid[0], r_bid[0], v)

                # Skip duplicates
                if key in yielded: continue

                # New guard test
                r_fn = sdg.fn_lookup[r_bid[0]]

                # Constructor reads don't race
                if r_fn.is_constructor or r_fn.name.startswith("initialize"): continue
                
                # Keep pair if variable is in any branch-group
                bg_set = sdg.var_to_branchgroups.get(v, set())
                if isinstance(v, MappingSlotVar): bg_set |= sdg.var_to_branchgroups.get(v.base, set())
                if bg_set:
                    affects = True
                else:
                    affects = read_affects_state(sdg, r_bid, v) or called_from_stateful(r_fn, sdg)
                if not affects: continue

                # Same block has both read and write
                if w_bid in reads: continue
                pattern = "stale_read" if w_bid < r_bid else "destructive_write"

                # No-op write pruning
                if NOOP_WRITE_FILTER:
                    w_fn = sdg.fn_lookup[w_bid[0]]
                    w_node = node_by_id(w_fn, w_bid[1])
                    if w_node is not None and is_self_copy_write(v, w_node): continue

                # Require key overlap if both sides touch slots of >=1 common base mapping
                if REQUIRE_SAME_SLOT_KEY:
                    w_keys, r_keys = slot_keys_at(sdg, w_bid, "writes"), slot_keys_at(sdg, r_bid, "reads")
                    common = set(w_keys.keys()) & set(r_keys.keys())
                    if common and not any(w_keys[b] & r_keys[b] for b in common): continue

                # If outer entries don't match, it is a cross-transaction pattern
                if pattern == "stale_read" and outer_entry(w_bid[0]) != outer_entry(r_bid[0]):
                    pattern = 'cross_tx_stale_read'

                yielded.add(key)

                # [DEBUG] to find 112, we check if we're producing balances/actionLockedBalances
                # if {v.name, getattr(v, "base", None) and v.base.name} & {"balances", "actionLockedBalances"}:
                #     print(f"[pair#112] {pattern}  W={w_bid} R={r_bid}  var={v.name}")

                yield (w_bid, r_bid, v, pattern)