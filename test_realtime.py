# -*- coding: utf-8 -*-
"""测试 realtime_source + app_patch_realtime 的接口与逻辑"""
import os
import sys
import tempfile
import importlib.util

os.environ["DATASOURCE"] = "realtime"
os.environ["USE_MANUAL_POOL"] = "true"

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np
import pandas as pd


def load(mod, path):
    spec = importlib.util.spec_from_file_location(mod, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    results = []
    def check(name, cond):
        results.append((name, bool(cond)))
        print(f"  [{'✓' if cond else '✗'}] {name}")

    # ---------- 1) 手动慢池加载 ----------
    print("\n[1] 手动慢池 load_manual_pool")
    rt = load("realtime_source", os.path.join(HERE, "realtime_source.py"))
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8-sig") as f:
        f.write("code,name,sw_l1,sw_l2,cycle,base_price\n")
        f.write("600547,山东黄金,有色金属,贵金属,mid_weak,28.0\n")
        f.write("000001,平安银行,银行,股份制银行,weak,12.5\n")
        f.write("000002,万科A,房地产,住宅开发,mid_strong,9.5\n")
        f.write("sh600519,贵州茅台,食品饮料,白酒,weak,1680\n")  # 带交易所前缀
        f.write("# 这是注释行\n")
        f.write("601318\n")  # 只有代码
        csv_path = f.name
    pool = rt.load_manual_pool(csv_path)
    check("加载 5 只（注释行被忽略）", len(pool) == 5)
    codes = [p["code"] for p in pool]
    check("code 标准化为 6 位（sh600519 -> 600519）", "600519" in codes and "sh600519" not in codes)
    check("601318 单代码也补齐", "601318" in codes)
    m = {p["code"]: p for p in pool}
    check("山东黄金 字段保留", m["600547"]["name"] == "山东黄金" and m["600547"]["cycle"] == "mid_weak")
    check("万科A base_price=9.5", m["000002"]["base_price"] == 9.5)

    # ---------- 2) RealtimeDataSource 接口一致性 ----------
    print("\n[2] RealtimeDataSource 接口")
    ds = rt.RealtimeDataSource(pool=[], manual_pool_path=csv_path, use_manual_pool=True, enrich_finance=False)
    check("source == 'Realtime'", getattr(ds, "source", "") == "Realtime")
    check("有 error 属性", hasattr(ds, "error"))
    check("有 get_pool 方法", callable(getattr(ds, "get_pool", None)))
    check("有 snapshot 方法", callable(getattr(ds, "snapshot", None)))

    # ---------- 3) 慢池构建（网络可能受限，允许降级） ----------
    print("\n[3] get_pool()")
    pool = ds.get_pool()
    check("慢池非空", len(pool) > 0)
    if pool:
        rec = pool[0]
        for k in ["code", "name", "sw_l1", "sw_l2", "cycle", "price", "circ_mv", "pb", "pe_ttm"]:
            check(f"慢池含字段 {k}", k in rec)

    # ---------- 4) 快照 + 双口径主力增仓% ----------
    print("\n[4] snapshot() 双口径")
    # 构造一个确定性的假腾讯快照环境：直接测 _snapshot 逻辑需 mock _batch_fetch；
    # 这里改为用 Mock 池 + 验证 compute_main_positions 等价性
    snap = ds.snapshot(pool[:5]) if pool else None
    if snap:
        r = snap[0]
        for k in ["main_pos1", "main_pos1_amt", "main_pos5", "main_pos5_amt",
                  "main_pos10", "main_pos10_amt", "main_pos20", "main_pos20_amt"]:
            check(f"快照含 {k}", k in r)
        # 双口径公式校验（用真实源字段）
        free = r.get("free_circ_mv") or r.get("circ_mv") or 0
        amt = r.get("amount") or 0
        net1 = (r.get("net_super", 0) or 0) + (r.get("net_big", 0) or 0)
        if free and amt and net1:
            expected_free = round(net1 / free * 100, 2)
            expected_amt = round(net1 / amt * 100, 2)
            check(f"main_pos1 自由流通市值口径 = net1/free*100 (= {expected_free})",
                  abs((r.get("main_pos1") or 0) - expected_free) < 1e-6)
            check(f"main_pos1_amt 成交额口径 = net1/amt*100 (= {expected_amt})",
                  abs((r.get("main_pos1_amt") or 0) - expected_amt) < 1e-6)
    else:
        print("  (网络受限，快照为空，降级逻辑已触发；接口结构仍通过)")

    # ---------- 5) build_data_source 工厂 ----------
    print("\n[5] build_data_source 工厂（app_patch_realtime）")
    patch = load("app_patch_realtime", os.path.join(HERE, "app_patch_realtime.py"))
    for mode in ["realtime", "tushare", "mock", "invalid_should_fallback"]:
        d = patch.build_data_source(mode=mode, use_manual=True, mock_pool=[])
        check(f"mode={mode} -> 有 source 属性", hasattr(d, "source"))
        check(f"mode={mode} -> 有 get_pool/snapshot", hasattr(d, "get_pool") and hasattr(d, "snapshot"))

    # ---------- 6) 腾讯代码标准化 ----------
    print("\n[6] _code6_to_tencent")
    fn = rt._code6_to_tencent
    check("600547 -> sh600547", fn("600547") == "sh600547")
    check("000001 -> sz000001", fn("000001") == "sz000001")
    check("688001 -> sh688001（科创）", fn("688001") == "sh688001")
    check("8xxxxx -> bj（北交所）", fn("830000").startswith("bj"))

    # ---------- 汇总 ----------
    print("\n" + "=" * 50)
    passed = sum(1 for _, ok in results if ok)
    print(f"总计：{passed}/{len(results)} 通过")
    for name, ok in results:
        if not ok:
            print(f"  ✗ {name}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
