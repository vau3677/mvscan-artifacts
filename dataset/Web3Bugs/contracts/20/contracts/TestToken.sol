// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.3;

import "./interfaces/iBEP20.sol";

contract TestToken is iBEP20 {
    string public constant override name = "TestToken";
    string public constant override symbol = "TTKN";
    uint8  public constant override decimals = 18;

    uint256 public override totalSupply;
    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;

    function balanceOf(address account) public view override returns (uint256) {
        return _balances[account];
    }

    function allowance(address owner, address spender) public view override returns (uint256) {
        return _allowances[owner][spender];
    }

    function transfer(address recipient, uint256 amount) public override returns (bool) {
        _transfer(msg.sender, recipient, amount);
        return true;
    }

    function approve(address spender, uint256 amount) public override returns (bool) {
        _allowances[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transferFrom(address sender, address recipient, uint256 amount) public override returns (bool) {
        uint256 allowed = _allowances[sender][msg.sender];
        require(allowed >= amount, "allowance");
        _allowances[sender][msg.sender] = allowed - amount;
        _transfer(sender, recipient, amount);
        return true;
    }

    function burn(uint256 amount) external override {
        require(_balances[msg.sender] >= amount, "balance");
        _balances[msg.sender] -= amount;
        totalSupply -= amount;
        emit Transfer(msg.sender, address(0), amount);
    }

    // --- test mint helper ---
    function mint(address to, uint256 amount) external {
        _balances[to] += amount;
        totalSupply += amount;
        emit Transfer(address(0), to, amount);
    }

    // --- internal transfer ---
    function _transfer(address from, address to, uint256 amount) internal {
        require(from != address(0) && to != address(0), "zero");
        require(_balances[from] >= amount, "balance");
        _balances[from] -= amount;
        _balances[to] += amount;
        emit Transfer(from, to, amount);
    }
}
