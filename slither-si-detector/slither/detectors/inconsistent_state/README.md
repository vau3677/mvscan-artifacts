# Static Slither Inconsistent State Detector

## Author: Vladislav Usatii

## Overview

A static inconsistent state detector for Eth contracts that builds an SDG atop each function's CFG, prunes to externally reachable paths, and utilizes forward-slicing to keep read/write interactions which drive control-flow or external-call divergence. Detects stale-read and destruive-write reaces including cross-function reentrancy support. Buckets issues by transaction sets and multi-variable groups and emits exploit-ready JSON with slots, selectors, and source locations for future validation via dynamic exploit generation.

## Approach

This Inconsistent State Detector performs the following high-level steps:

1. Builds SDG.

- Traverses each function's CFG and adds nodes/edges to the SDG for all state variable accesses.
- Every basic block of every function gets a consideration, as does its read and write operations on storage.

2. Prune unreachable nodes.

- Finds all basic blocks reachable from public or external functions. It treats only truly externally callable functions as entry points, so we exclude ownerOnly and a few other names.
- Removes any nodes and edges from the SDG that lie entirely in unreachable code.
- We get a graph of how an attacker can change contract state.

3. Identify dangerous pairs.

- Searches pruned SDG for all pairs of operations (nodes) on the same storage variable or pseudo-variable group.
- Consider a pair as a candidate hazardous access pair (i.e. stale read, destructive write) iff one of the operations is a write.
- Every pair has two transactions, which can be used later to test true positives.

4. Apply divergence filter.

- For every candidate where a read occurs, do a forward data-flow analysis (i.e. forward-slice) from the read to check if it influences a control-flow branch or an external call later down the line in the function's execution.
- If it doesn't influence anytime later down the line, discard the pair and label it as non-exploitable.
- We are filtering cases where a read doesn't matter for a program decision (benign or infeasible as well).

5. Classify potential reentrancies.

- Check call graph for reentrancy relations between the functions in each remaining, unfiltered pair.
- If one function can potentially make an external call into the other or into itself during execution, it is marked as potentially reentrant.
- A reentrant_stale_read could involve seeing an external call in f that targets g or g to f.

6. Group pairs by the transaction set.

- If some function f() writes X and g() reads X from a hazardous pair, they are placed in a "bucket" {f, g} as the transaction set.
- Each bucket is a unique combo of entry points that might collectively or partially lead to an inconsistent state in our dynamic analysis step.
- In each bucket, there may exist multiple or groups of variables involved, especially if an invariant spans several variables. The detector can label the bucket with a pattern classification:
  * ```single_var_cross_tx``` 1 state variable without grouping is involved. This is a race on 1 variable across 2 distinct transactions.
  * ```multi_var_intra_contract``` Multiple variables as a group are involved, but they are all in the same contract, which indicates a potential invariant violation within one contract.
  * ```multi_var_cross_contract``` Multiple variables across different contracts are involved. Particularly, where an inconsistency spans many contracts. Although a rare find, it is possible if we consider interactions across contract calls or storage.
- We aggregate all hazardous pairs that involve the same transactions and variables. This gives a high-level overview of potential exploit scenarios that we can recreate in the dynamic exploit reproduction step.

7. Prepare result entries with the following:

- Pattern (e.g. single-var race, multi-var invariant)
- Variables: all state variables involved. Provide metadata including whether it is a direct state variable, part of a mapping, external contract's storage, pseudo-group, etc. It includes the storage slot number or does a fallback computation of it.
- Transaction Set: list of public function calls that form the exploit scenario.
- Hazardous Operations: provides details on program locations of the w/r operations that form the inconsistency. Includes a function signature and a 4-byte selector as reference, as well as the file location of every write and read.
- Operation Pattern Tags: Notes whether the underlying pair was a stale read or destructive write (or a re-entrant variant).
- Reentrancy and Shared-Call Indicator: Notes if the scenario involves reentrancy and if the two functions share a common internal call. A shared callee might signify the two operations affect the same sub-component elsewhere, which is additional context for successfully reproducing the bug.

- By canonicalizing and grouping all results, we avoid duplicate findings.

8. JSON output format (ISD_JSON_OUT=filename):

- ```pattern``` Bucket classification
- ```vars``` Array of variable metadata involved. Every variable can have a name, kind, slot, base_slot, branch_groups, and members.
- ```tx_set``` List of tx entry names, each corresponding to a public function, that form an attack schedule.
- ```writers``` ```readers``` Lists of objects detailing write and read operations in the pair. Each entry has a sig, selector, file, and line.
- ```op_patterns``` Specific low-level patterns of the hazardous operations involved; might list a different tag based on a different scenario type.
- ```shape``` Indicators of certain scenario shapes, including a reentrancy check and a shared_callee check.
- ```shape_by_var``` Array giving the shape on a per-variable basis; used for multi-variable cases to see which variable's pair caused reentrancy.

- The JSON is formatted for easy entry into a dynamic system, but can be modified or extended.

## Questions for Prof. Liu

What could we add to advance state-of-the-art?

Is the current state inconsistency definition too broad or narrow? Can it be refined?

Is it a good idea to remain at the intermediate representation level, or static single assignment?
- We are currently working with Slither's IR nodes like HighLevelCall and InternalCall and tracking r/w with StateVariable objects.
- I think your iteration was built on SSA and might be better in certain contexts, but I don't know what those contexts are.

Can what we've built be extended to anything new? Any interesting ideas there?

How do we run the detector on large datasets? Any shortcuts?

Can we generalize this beyond EVM? Might be beyond the scope of the research, but would be incredibly useful in decentralized systems.


### How to run

```
git clone https://github.com/rit-seclab/slither-si-detector/tree/vlad_development.git # my development branch
cd contract_example # replace with your contract codebase
vi hardhat.config.js
```

Within hardhat.config.js, we need to allow a few things to be tracked in our output. This is because JSON artifacts include a storageLayout section detailing each state variable’s slot and offset, but it must be manually set in older versions of Slither.

```json
module.exports = {
  solidity: {
    version: "0.8.x",
    settings: {
      outputSelection: {
        "*": { "*": ["storageLayout"] }
      }
    }
  }
};
```

Now return to your root directory. Compile and run the detector:

```
npx hardhat clean && npx hardhat compile # compile your project
ISD_JSON_OUT=out.json slither . --detect inconsistent_state --hardhat-ignore-compile
cat out.json # we pass structured output into the exploit generator
```

