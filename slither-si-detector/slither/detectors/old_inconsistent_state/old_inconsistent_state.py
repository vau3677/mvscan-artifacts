from typing import List
import itertools

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification
from slither.utils.output import Output
from slither.core.variables import StateVariable
from slither.core.declarations.function_contract import FunctionContract
from slither.core.source_mapping.source_mapping import Source


def check_existence(state_info: dict, v: StateVariable, source_name: str) -> None:
    if source_name not in state_info:
        state_info[source_name] = dict()
    if v not in state_info[source_name]:
        state_info[source_name][v] = dict()


def is_write(code: str, v_name: str) -> bool:
    code = code.replace("==", "")
    if code.__contains__("=") and code.split("=")[0].__contains__(v_name):
        return True
    return False


def is_require(code: str, v_name: str) -> bool:
    for item in code.partition("require(")[2].rpartition(")")[0].split(","):
        if item.__contains__(v_name):
            return True
    return False


def update_state_setting(state_info: dict, v: StateVariable, line_of_code: str, source_name: str, line: int) -> None:
    if line_of_code == "":
        return
    if is_write(line_of_code, v.name) or is_require(line_of_code, v.name):
        check_existence(state_info, v, source_name)
        state_info[source_name][v][line] = line_of_code
    # [TODO] Consider more cases


def update_source(source_dict: dict, v: StateVariable) -> None:
    location = v.source_mapping.filename
    if location in source_dict:
        source_dict[location].append(v)
    else:
        source_dict[location] = [v]


FILTER_INTERNAL = True
FILTER_NON_EXTERNAL = True
FILTER_ONLY = True
FILTER_INITIALIZER = True


def find_entry(function: FunctionContract) -> FunctionContract:
    content = get_func_head(function).lower()
    if FILTER_INTERNAL and function.visibility == "internal":
        for func in function.reachable_from_functions:
            entry = find_entry(func)
            if entry is not None:
                return entry
        return None
    if FILTER_NON_EXTERNAL and function.visibility != "external":
        return None
    if FILTER_ONLY and content.__contains__("only"):
        return None
    if FILTER_INITIALIZER and content.__contains__("initializer"):
        return None
    # [TODO] need more rules
    return function


def rw_assignment(line: int, v: StateVariable, r_dict: dict, w_dict: dict, function: FunctionContract) -> None:
    source = function.source_mapping
    line_of_code = str(source.compilation_unit.crytic_compile.get_code_from_line(
        source.filename, line))
    v_name = v.name
    target_dict = None
    if is_write(line_of_code, v_name):
        target_dict = w_dict
    else:
        target_dict = r_dict
    if v not in target_dict:
        target_dict[v] = set()
    target_dict[v].add(function)


def update_stateful_func(function: FunctionContract, func_statful_ops: dict(), stateful_source: dict()) -> bool:
    func_statful_ops[function] = None

    # filter slither functions
    if function.name == "slitherConstructorConstantVariables" or function.name == "slitherConstructorVariables":
        return False

    func_src = function.source_mapping
    func_lines = set(func_src.lines)
    filename = func_src.filename

    # all ops are stateful if the function is called statefully
    if function.visibility == "internal":
        for parent_node in function.reachable_from_nodes:
            parent_func = parent_node.node.function
            if parent_func not in func_statful_ops:
                update_stateful_func(
                    parent_func, func_statful_ops, stateful_source)
            parent_states = func_statful_ops[parent_func]
            if parent_states is not None and max(parent_node.ir.expression.source_mapping.lines) > min(parent_states):
                func_statful_ops[function] = func_lines
                return True

    # Find ranges of state and data
    if filename in stateful_source:
        stateful_info = stateful_source[filename]
        stateful_lines = set()
        for tmp in stateful_info.values():
            stateful_lines.update(tmp.keys())
        state_locs = func_lines.intersection(
            stateful_lines)
        if len(state_locs) > 0:
            func_statful_ops[function] = state_locs
            return True

    return False


def has_data_access(data_access_source: dict, filename: str, func_lines: set) -> bool:
    if filename not in data_access_source.keys():
        return False
    data_lines = set(itertools.chain.from_iterable(
        data_access_source[filename].values()))
    data_locs = set(data_lines.intersection(func_lines))
    if len(data_locs) > 0:
        return True
    return False


def get_source_code(source: Source) -> str:
    source_name = source.filename
    line_of_code = ""
    for line in source.lines:
        line_of_code += str(source.compilation_unit.crytic_compile.get_code_from_line(
            source_name, line))
    return line_of_code


def get_func_head(function: FunctionContract) -> str:
    src_mapping: Source = function.source_mapping
    content: str = get_source_code(src_mapping)
    return content.split(')')[1].split('{')[0]


def is_state_var(v: StateVariable) -> bool:
    if str(v._type) == "bool":
        return True
    for source in v.references:
        if is_require(get_source_code(source), v.name):
            return True
    # [TODO] change the rule for identifying state variables
    return False


class OldInconsistentState(AbstractDetector):
    """
    Detect the inconsistent states
    """

    ARGUMENT = 'old_inconsistent_state'  # slither will launch the detector with slither . --detect old_inconsistent_state
    HELP = 'Old inconsistent state detector'
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.HIGH

    WIKI = '..'
    WIKI_TITLE = 'Old inconsistent state detector'
    WIKI_DESCRIPTION = 'Plugin testing'
    WIKI_EXPLOIT_SCENARIO = '..'
    WIKI_RECOMMENDATION = '..'

    def _detect(self) -> List[Output]:
        results = []

        for contract in self.compilation_unit.contracts_derived:
            if contract.contract_kind == "contract":
                # divide state_variables from data_variables
                state_source = dict()  # source_name -> list of v
                data_source = dict()  # source_name -> list of d
                for v in contract._variables_ordered:
                    if is_state_var(v):
                        update_source(state_source, v)
                    # Check other state variables (including boolean functions)
                    else:
                        update_source(data_source, v)
                    # [TODO] Consider whether state variables are also data variables

                # We only focus on files that contain both state variables and data variables
                # target_source = set(state_source.keys()).intersection(
                #     set(data_source.keys()))
                # state_source[source] for source in target_source))
                state_variables = list(
                    itertools.chain.from_iterable(state_source.values()))

                # Collect stateful source and stateful locations
                stateful_source = dict()  # source_name -> v -> line -> state_value
                for v in state_variables:
                    # Get the modification/require of the definition
                    for source in v.references:  # slither.core.source_mapping.source_mapping.Source object
                        # Get the scopes divided by the value of the uses
                        update_state_setting(
                            stateful_source, v, get_source_code(source), source.filename, max(source.lines))

                # Collect data access locations
                data_access_source = dict()  # source_name -> v -> list of lines
                for d in itertools.chain.from_iterable(data_source.values()):
                    for source in d.references:
                        if source.filename not in data_access_source:
                            data_access_source[source.filename] = dict()
                        if d not in data_access_source[source.filename]:
                            data_access_source[source.filename][d] = []
                        data_access_source[source.filename][d] += source.lines

                stateful_r = dict()
                stateful_w = dict()
                stateless_r = dict()
                stateless_w = dict()

                func_statful_ops = dict()  # collect state setting ops in each func

                for function in contract.functions:
                    func_src = function.source_mapping
                    filename = func_src.filename
                    func_lines = set(func_src.lines)
                    if not has_data_access(data_access_source, filename, func_lines):
                        continue

                    if function in func_statful_ops and func_statful_ops[function] is not None or update_stateful_func(function, func_statful_ops, stateful_source):
                        state_locs = func_statful_ops[function]
                        for d, lines in data_access_source[filename].items():
                            source = set(lines) & func_lines
                            if len(source) > 0:
                                entry_func = find_entry(function)
                                if entry_func is not None:
                                    # Check if restriction exist before op
                                    if max(lines) > min(state_locs):
                                        for l in source:
                                            rw_assignment(
                                                l, d, stateful_r, stateful_w, entry_func)
                                    else:
                                        for l in source:
                                            rw_assignment(
                                                l, d, stateless_r, stateless_w, entry_func)
                        # Find the use of data variable in range
                    else:
                        # No state restriction
                        for d, lines in data_access_source[filename].items():
                            source = set(lines) & func_lines
                            if len(source) > 0:
                                entry_func = find_entry(function)
                                if entry_func is not None:
                                    for l in source:
                                        rw_assignment(
                                            l, d, stateless_r, stateless_w, entry_func)

                var_info = dict()
                stateless_func = set()

                def collect_results(stateful_op, stateless_op, stateful_op_name, stateless_op_name) -> None:
                    for global_variable in set(stateful_op.keys()).intersection(set(stateless_op.keys())):
                        # Info to be printed
                        if global_variable not in var_info:
                            var_info[global_variable] = [
                                "Found variable ", global_variable]
                        var_info[global_variable] += [" in a stateful ", stateful_op_name, " in "] + list(stateful_op[global_variable]) + [
                            " while also in a stateless ", stateless_op_name, " in ", ] + list(stateless_op[global_variable]) + ["\n"]
                        stateless_func.update(stateless_op[global_variable])

                collect_results(stateful_r, stateless_w, "read", "write")
                collect_results(stateful_w, stateless_r, "write", "read")
                collect_results(stateful_w, stateless_w, "write", "write")

                for info in var_info.values():
                    # Add the result in result
                    res = self.generate_result(info)
                    results.append(res)

                for func in stateless_func:
                    info = ["Stateless function ", func,
                            ": ", get_func_head(func), "\n"]
                    res = self.generate_result(info)
                    results.append(res)

        return results
