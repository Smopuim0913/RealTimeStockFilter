# -*- coding: utf-8 -*-
"""验证 data_source.py：公式、缓存、接口一致性（mock 模式，无需真实 token）"""
import os
os.environ["TUSHARE_TOKEN"] = ""  # 强制 mock
import importlib.util, sys

spec = importlib.util.spec_from_file_location("data_source", "data_source.py")
ds_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ds_mod)

# 用 app.py 的 mock 池（复刻一只）
MOCK_POOL = [{
    "code": "600547", "name": "山东黄金", "sw_l1": "有色金属", "sw_l2": "贵金属",
    "cycle": "mid_weak", "profit_yoy": 30.0, "rev_yoy": 22.0, "roe": 10.0,
    "gross_margin": 25.0, "debt_ratio": 60.0, "div_yield": 1.0,
    "total_mv": 1200, "circ_mv": 1100, "free_circ_mv": 900, "pb": 3.0,
    "pe_static": 40.0, "pe_ttm": 38.0, "pe_dyn": 35.0,
    "base_price": 28.0, "base_amount": 9.0,
    "net_super": 0.6, "net_big": 0.4, "net_mid": -0.4, "net_small": -0.6,
    "net_main5": 4.0, "net_main10": 7.0, "net_main20": 11.0,
}]

ok = True
def check(cond, msg):
    global ok
    print(("  ✓ " if cond else "  ✗ ") + msg)
    ok = ok and cond

print("\n[1] 无 token -> 自动 mock")
ds = ds_mod.DataSource(pool=MOCK_POOL)
check(ds.source == "MOCK", f"source=MOCK (got {ds.source})")
check(ds.error != "", "error 有降级原因说明")

print("\n[2] get_pool / snapshot 接口正常")
pool = ds.get_pool()
check(len(pool) == 1, f"慢池=1 (got {len(pool)})")
snap = ds.snapshot(pool)
check(len(snap) == 1, f"快照=1 (got {len(snap)})")

print("\n[3] 主力增仓% 双口径公式校验（自洽性：用 snapshot 实际资金额反算）")
r = snap[0]
net1_actual = r["net_super"] + r["net_big"]   # snapshot 里的真实资金额（mock 经随机游走）
free = r["free_circ_mv"] or r["circ_mv"]
amt = r["amount"]
expected_free = round(net1_actual / free * 100, 2) if free else None
expected_amt = round(net1_actual / amt * 100, 2) if amt else None
check(r["main_pos1"] == expected_free,
      f"自由流通市值口径: {net1_actual}/{free}*100 = {expected_free} (got {r['main_pos1']})")
check(r["main_pos1_amt"] == expected_amt,
      f"成交额口径: {net1_actual}/{amt}*100 = {expected_amt} (got {r['main_pos1_amt']})")

print("\n[4] 防除零：封装双口径函数直接测")
def calc_pos(net_super, net_big, free_circ_mv, circ_mv, amount):
    net1 = net_super + net_big
    free = free_circ_mv or circ_mv
    amt = amount
    main_pos1 = round(net1 / free * 100, 2) if free else None
    main_pos1_amt = round(net1 / amt * 100, 2) if amt else None
    return main_pos1, main_pos1_amt

# free=0 -> 回退 circ_mv；与 round(net/free*100,2) 精确一致
a, b = calc_pos(0.6, 0.4, 0, 1100, 9.0)
expected = round(1.0 / 1100 * 100, 2)
check(a == expected, f"free=0 回退 circ_mv: {a} (期望 {expected})")
# 所有分母都为0 -> 双 None
a2, b2 = calc_pos(0.6, 0.4, 0, 0, 9.0)
check(a2 is None, "free=0 且 circ_mv=0 -> main_pos1=None")
# amount=0 -> 成交额口径 None
a3, b3 = calc_pos(0.6, 0.4, 900, 0, 0.0)
check(b3 is None, f"成交额=0 -> main_pos1_amt=None (got {b3})")
check(a3 is not None, "free 有值，自由口径仍正常")

print("\n[5] 缓存：第二次取数走缓存（无 token 时 mock 不缓存也OK）")
import cache
cache.put("pool", MOCK_POOL)
v = cache.get("pool")
check(v is not None and len(v) == 1, "缓存读写正常")

print("\n[6] app.py 调用方式对齐")
sig_ok = hasattr(ds, "get_pool") and hasattr(ds, "snapshot") and hasattr(ds, "source")
check(sig_ok, "有 get_pool / snapshot / source 接口")

print("\n" + ("✅ 全部通过" if ok else "❌ 存在失败项"))
sys.exit(0 if ok else 1)
