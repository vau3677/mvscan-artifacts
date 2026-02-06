"""
ir.py
Goal: Better checks using Slither's IR to enable high precision
"""
from slither.slithir.operations import OperationWithLValue
from slither.core.cfg.node import NodeType
from slither.core.variables.state_variable import StateVariable
from slither.core.cfg.node import Node

# Returns iff basic block writes directly to storage var v
def is_write(node: Node, v: StateVariable) -> bool:
    for ir in node.irs:
        if not isinstance(ir, OperationWithLValue): continue
        if ir.lvalue != v: continue

        # Self-assignment check
        if getattr(ir, "reads", None) and set(ir.reads) == {v}: continue

        # Idempotence check
        op = getattr(ir, "operation", "").upper()
        imm = getattr(ir, "immediate", None)
        if op in ("ADD", "SUB") and imm == 0 and set(ir.reads) == {v}: continue
        if op in ("MUL", "DIV") and imm == 1 and set(ir.reads) == {v}: continue

        # Map default write check (key normalized equality covers slot alias)
        if set(ir.reads) and all(r == ir.lvalue for r in ir.reads): continue
        return True
    return False

# returns iff v is read in a conditional that can alter the control flow
def is_require(node: Node, v: StateVariable) -> bool:
    if node.type in (NodeType.IF, NodeType.REQUIRE, NodeType.ASSERT, NodeType.REVERT):
        return (v in node.expression.variables_read)
    return False
