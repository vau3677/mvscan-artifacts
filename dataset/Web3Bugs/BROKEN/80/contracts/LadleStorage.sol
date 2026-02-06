// SPDX-License-Identifier: MIT
pragma solidity 0.8.6;

import "@yield-protocol/vault-interfaces/ICauldron.sol";
import "@yield-protocol/utils-v2/contracts/token/IWETH9.sol";

contract LadleStorage {
    ICauldron public cauldron;
    IWETH9 public weth;
    bytes12 public cachedVaultId;

    constructor(ICauldron cauldron_, IWETH9 weth_) {
        cauldron = cauldron_;
        weth = weth_;
    }
}
