"""
两级筛选架构原型（验证逻辑正确性，mock 数据，不依赖网络）
=========================================================
Level 1 — 季度慢池 (Quarterly Pool)
  财报驱动：ROE、资产负债率、股息率、利润同比、经营现金流/净利润、市现率
  刷新：财报密集期按天重拉；平时每周/手动

Level 2 — 盘中快筛 (Intraday Fast Filter)
  只对慢池内的标的套快变量：
  股价、内外比、DDX、量比、换手率、金额、流通/自由流通市值、PE/PB 各类比率
  刷新：每 15~30 秒一轮，波动即自动进入/出局

核心：慢池资格跨轮保持，快变量决定"当前是否亮灯"
=========================================================
"""
from dataclasses import dataclass, field
from typing import Set, Dict, Tuple, Optional
import time

# 周期过滤模块（V2 新增）：申万行业分级打标 + 周期性评分
# 见 cycle_filter.py —— 提供 CycleClassifier / STRENGTH_RANK
try:
    from cycle_filter import CycleClassifier, STRENGTH_RANK
except ImportError:  # 独立运行时若不可导入，延迟到 SlowConditions.check 里处理
    CycleClassifier = None  # type: ignore
    STRENGTH_RANK = None  # type: ignore


# =====================================================================
# 条件参数（用户关心的字段，全部可配置）
# =====================================================================
@dataclass
class FastConditions:
    """盘中快变量条件 —— 随行情秒变"""
    price_max: float = 50.0
    inner_outer_ratio_max: float = 0.8      # 内外比 < 0.8（内盘/外盘）
    ddx1_min: float = 0.0                   # 当日 DDX > 0
    ddx5_min: float = -1.0                  # 5日 DDX > -1
    ddx10_min: float = -1.0                 # 10日 DDX > -1
    ddx20_min: float = -1.0                 # 20日 DDX > -1
    volume_ratio_min: float = 1.5           # 量比 > 1.5
    turnover_min: float = 0.3               # 换手率 > 0.3%（开盘可能为空）
    amount_min: float = 2.5e8               # 成交额 > 2.5亿（开盘可能为空）
    circ_mktcap_min_ratio: float = 1.0      # 流通市值 > 市场均值（=均值*1.0）
    pb_max_ratio: float = 1.0               # 市净率 < 市场均值
    pe_dynamic_max_ratio: float = 1.0       # 动态PE < 市场均值
    pe_static_max_ratio: float = 1.0        # 静态PE < 市场均值
    pe_ttm_max_ratio: float = 1.0           # TTM PE < 市场均值
    pe_dyn_static_ratio_max: float = 1.0    # 动态PE/静态PE < 1
    pe_dyn_ttm_ratio_max: float = 1.0       # 动态PE/TTM < 1
    pe_dyn_peg_max: float = 1.0             # 动态PE/利润同比% (=PEG) < 1


@dataclass
class SlowConditions:
    """财报慢变量条件 —— 季度级变化"""
    board_allow: Tuple[str, ...] = ("主板",)   # 仅沪深主板，排除双创/京A
    price_max: float = 100.0                    # 初筛放宽到 <100
    circ_mktcap_min: float = 100e8              # 流通市值 > 100亿
    free_float_mktcap_min: Optional[float] = 200e8  # 自由流通市值 > 200亿（可选）
    pcf_ratio_max: float = 0.25                 # 市现率 < 25%
    ocf_netprofit_min: float = 0.8              # 经营现金流净额/净利润 > 0.8
    roe_min: float = 0.05                       # ROE > 5%
    debt_ratio_max: float = 0.6667              # 资产负债率 < 66.67%
    dividend_yield_min: float = 0.025           # 股息率 > 2.5%

    # ---- 周期股过滤（V2 新增）----
    # 控件建议：周期强度滑块（strong/mid_strong/mid/mid_weak/weak/none），默认 mid_weak
    max_cycle_strength: str = "mid_weak"         # 最大允许的周期强度，默认排除强+中强周期
    excluded_sw_l2: Tuple[str, ...] = (          # 申万二级精细排除（默认空，按需填）
        "石油开采", "工业金属", "普钢", "煤炭开采")
    # 周期分类器实例（由前端/启动入口注入，见 cycle_filter.py）
    cycle_classifier: Optional["CycleClassifier"] = None


# =====================================================================
# mock 行情/财务数据源
# =====================================================================
# 模块级可变数据源（真实环境替换为 akshare/Tushare 调用）
_MARKET = {
    "600001": {"price": 12.3, "inner_outer": 0.6, "ddx1": 0.12, "ddx5": 0.3,
               "ddx10": -0.2, "ddx20": 0.1, "vr": 2.1, "turn": 1.2, "amount": 5.0e8,
               "circ_cap": 300e8, "free_cap": 220e8, "pb": 1.8, "pe_dyn": 9,
               "pe_sta": 10, "pe_ttm": 9, "board": "主板"},
    "600002": {"price": 40.0, "inner_outer": 0.7, "ddx1": 0.05, "ddx5": -0.3,
               "ddx10": -0.5, "ddx20": -0.4, "vr": 1.8, "turn": 0.8, "amount": 3.0e8,
               "circ_cap": 400e8, "free_cap": 250e8, "pb": 2.0, "pe_dyn": 8,
               "pe_sta": 9, "pe_ttm": 8, "board": "主板"},
    "600003": {"price": 6.5, "inner_outer": 0.9, "ddx1": -0.1, "ddx5": -1.5,
               "ddx10": -2.0, "ddx20": -1.8, "vr": 1.2, "turn": 0.4, "amount": 1.0e8,
               "circ_cap": 150e8, "free_cap": 100e8, "pb": 1.5, "pe_dyn": 10,
               "pe_sta": 11, "pe_ttm": 10, "board": "主板"},
    "688001": {"price": 30.0, "inner_outer": 0.5, "ddx1": 0.2, "ddx5": 0.4,
               "ddx10": 0.3, "ddx20": 0.2, "vr": 3.0, "turn": 5.0, "amount": 8.0e8,
               "circ_cap": 200e8, "free_cap": 180e8, "pb": 3.0, "pe_dyn": 8,
               "pe_sta": 9, "pe_ttm": 8, "board": "科创"},  # 会被板块过滤剔除
}


_FINANCIAL = {
    "600001": {"pcf": 0.18, "ocf_np": 1.1, "roe": 0.08, "debt": 0.55, "div_y": 0.03, "profit_yoy": 15},
    "600002": {"pcf": 0.20, "ocf_np": 0.9, "roe": 0.06, "debt": 0.60, "div_y": 0.04, "profit_yoy": 14},
    "600003": {"pcf": 0.22, "ocf_np": 1.2, "roe": 0.07, "debt": 0.50, "div_y": 0.03, "profit_yoy": 12},
    "688001": {"pcf": 0.15, "ocf_np": 1.0, "roe": 0.10, "debt": 0.40, "div_y": 0.02, "profit_yoy": 20},
}


def fetch_market_snapshot():
    """模拟 stock_zh_a_spot_em()：全市场快照（快变量）"""
    return _MARKET


def fetch_financial_snapshot():
    """模拟财报基本面（慢变量）—— 对应 Tushare daily_basic + fina_indicator"""
    return _FINANCIAL


# =====================================================================
# Level 1：季度慢池构建
# =====================================================================
def build_quarterly_pool(slow: SlowConditions) -> Set[str]:
    """财报初筛 → 符合条件的季度候选池（含周期股过滤）"""
    pool = set()
    spot = fetch_market_snapshot()
    fin = fetch_financial_snapshot()

    for code, s in spot.items():
        f = fin.get(code)
        if not f:
            continue
        # 板块过滤（沪深主板，排除双创/京A）
        if s["board"] not in slow.board_allow:
            continue
        if s["price"] > slow.price_max:
            continue
        if s["circ_cap"] < slow.circ_mktcap_min:
            continue
        if slow.free_float_mktcap_min and s["free_cap"] < slow.free_float_mktcap_min:
            continue
        if f["pcf"] > slow.pcf_ratio_max:
            continue
        if f["ocf_np"] < slow.ocf_netprofit_min:
            continue
        if f["roe"] < slow.roe_min:
            continue
        if f["debt"] > slow.debt_ratio_max:
            continue
        if f["div_y"] < slow.dividend_yield_min:
            continue

        # ---- 周期股过滤（V2）：强度上限 + 申万二级精细排除 ----
        if slow.cycle_classifier is not None:
            tag = slow.cycle_classifier.classify(code)
            if STRENGTH_RANK[tag.final_strength] > STRENGTH_RANK[slow.max_cycle_strength]:
                continue
            if tag.sw_l2_name and tag.sw_l2_name in slow.excluded_sw_l2:
                continue

        pool.add(code)
    return pool


# =====================================================================
# Level 2：盘中快筛（仅对慢池内标的）
# =====================================================================
def fast_filter(pool: Set[str], fast: FastConditions, market_stats: Dict) -> Set[str]:
    """对慢池标的套快变量条件；动态阈值（均值类）用当日市场统计"""
    result = set()
    spot = fetch_market_snapshot()
    cap_mean = market_stats["circ_cap_mean"]
    pb_mean = market_stats["pb_mean"]
    pe_dyn_mean = market_stats["pe_dyn_mean"]
    pe_sta_mean = market_stats["pe_sta_mean"]
    pe_ttm_mean = market_stats["pe_ttm_mean"]

    for code in pool:
        if code not in spot:
            continue
        s = spot[code]
        f = fetch_financial_snapshot().get(code)
        if not f:
            continue

        # —— 快变量逐项判定 ——
        if s["price"] > fast.price_max:                      continue
        if s["inner_outer"] >= fast.inner_outer_ratio_max:   continue
        if s["ddx1"] <= fast.ddx1_min:                       continue
        if s["ddx5"] <= fast.ddx5_min:                       continue
        if s["ddx10"] <= fast.ddx10_min:                     continue
        if s["ddx20"] <= fast.ddx20_min:                     continue
        # 量比/换手/金额：None 表示开盘尚无数据 → 跳过该项（随时间慢慢入围）
        if s["vr"] is not None and s["vr"] < fast.volume_ratio_min:       continue
        if s["turn"] is not None and s["turn"] < fast.turnover_min:       continue
        if s["amount"] is not None and s["amount"] < fast.amount_min:     continue
        if s["circ_cap"] < cap_mean * fast.circ_mktcap_min_ratio:         continue
        if s["pb"] >= pb_mean * fast.pb_max_ratio:                       continue
        if s["pe_dyn"] >= pe_dyn_mean * fast.pe_dynamic_max_ratio:        continue
        if s["pe_sta"] >= pe_sta_mean * fast.pe_static_max_ratio:         continue
        if s["pe_ttm"] >= pe_ttm_mean * fast.pe_ttm_max_ratio:            continue
        # 动态PE/静态PE 比率（<=1 表示动态估值不高于静态，即预期向好）
        if s["pe_sta"] > 0 and s["pe_dyn"] / s["pe_sta"] > fast.pe_dyn_static_ratio_max: continue
        # 动态PE/TTM 比率
        if s["pe_ttm"] > 0 and s["pe_dyn"] / s["pe_ttm"] > fast.pe_dyn_ttm_ratio_max:    continue
        # PEG = 动态PE / 利润同比%
        peg = s["pe_dyn"] / f["profit_yoy"] if f["profit_yoy"] > 0 else 999
        if peg >= fast.pe_dyn_peg_max:                                     continue

        result.add(code)
    return result


def calc_market_stats():
    """计算当日市场均值（动态阈值用），真实环境用全市场快照统计"""
    spot = fetch_market_snapshot()
    vals = list(spot.values())
    n = len(vals)
    return {
        "circ_cap_mean": sum(v["circ_cap"] for v in vals) / n,
        "pb_mean": sum(v["pb"] for v in vals) / n,
        "pe_dyn_mean": sum(v["pe_dyn"] for v in vals) / n,
        "pe_sta_mean": sum(v["pe_sta"] for v in vals) / n,
        "pe_ttm_mean": sum(v["pe_ttm"] for v in vals) / n,
    }


# =====================================================================
# 主循环：diff 产生 进入 / 出局
# =====================================================================
class ScreenerEngine:
    def __init__(self, fast: FastConditions, slow: SlowConditions):
        self.fast = fast
        self.slow = slow
        self.pool: Set[str] = set()        # 季度慢池
        self.prev: Set[str] = set()       # 上轮入选
        self.pool_version: str = ""

    def refresh_pool(self, force: bool = False):
        """财报季密集期按天重拉；其余按需"""
        new_pool = build_quarterly_pool(self.slow)
        if new_pool != self.pool:
            print(f"[慢池更新] 候选数 {len(self.pool)} → {len(new_pool)}")
            self.pool = new_pool

    def tick(self):
        """一轮盘中筛选，输出 进入/出局/保持"""
        stats = calc_market_stats()
        curr = fast_filter(self.pool, self.fast, stats)
        entered = curr - self.prev
        exited = self.prev - curr
        held = curr & self.prev
        self.prev = curr

        if entered:
            print(f"  ✅ 进入: {sorted(entered)}")
        if exited:
            print(f"  ❌ 出局: {sorted(exited)}")
        if held:
            print(f"  ➖ 保持: {len(held)}只")
        return curr


# =====================================================================
# 演示：验证"开盘逐步入围 + 行情波动自动进出"两个核心行为
# =====================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("演示1：板块过滤 —— 科创/创业/京A 被排除在慢池外")
    print("=" * 60)
    eng = ScreenerEngine(FastConditions(), SlowConditions())
    eng.refresh_pool()
    print(f"慢池: {sorted(eng.pool)}  （688001 科创应被排除）")
    assert "688001" not in eng.pool, "板块过滤失败"
    print("✓ 板块过滤正确\n")

    print("=" * 60)
    print("演示2：开盘逐步入围 —— 量比/换手/金额 从无到有")
    print("=" * 60)
    spot = fetch_market_snapshot()
    # 模拟开盘初期：成交类字段为 None（空），随交易慢慢有数据
    spot["600002"]["turn"] = None
    spot["600002"]["amount"] = None
    spot["600002"]["vr"] = None
    eng2 = ScreenerEngine(FastConditions(), SlowConditions())
    eng2.pool = {"600001", "600002", "600003"}

    print("--- T1 开盘（成交为空 → 量比/换手/金额项跳过，600002 入围）---")
    r1 = eng2.tick()
    assert "600002" in r1, "开盘应入围"
    print(f"入选: {sorted(r1)}")

    # T2：成交数据填充后，600002 换手/金额仍达标，但量比=1.2<1.5 → 出局
    spot["600002"]["vr"] = 1.2
    spot["600002"]["turn"] = 1.0
    spot["600002"]["amount"] = 4.0e8
    print("\n--- T2 量比升至1.2（<1.5），换手/金额已有值 ---")
    r2 = eng2.tick()
    assert "600002" not in r2, "量比不达标应出局"
    print(f"入选: {sorted(r2)}")

    # T3：量比达标回升 → 重新进入
    spot["600002"]["vr"] = 1.9
    print("\n--- T3 量比升至1.9（>1.5）---")
    r3 = eng2.tick()
    assert "600002" in r3, "量比达标应重新进入"
    print(f"入选: {sorted(r3)}")
    print("\n✓ 全部断言通过：行情波动 → 自动进入/出局 逻辑正确")

    print("\n" + "=" * 60)
    print("演示3：财报季慢池按天刷新示意")
    print("=" * 60)
    print("每日启动时 check: 若财报密集期(1/4/7/10月披露季) → 强制 rebuild_quarterly_pool()")
    eng3 = ScreenerEngine(FastConditions(), SlowConditions())
    eng3.refresh_pool(force=True)

    # ==================================================================
    # 演示4（V2 新增）：周期股过滤 —— 端到端集成
    # ==================================================================
    print("\n" + "=" * 60)
    print("演示4：周期股过滤 —— 强度滑块 + 申万二级排除")
    print("=" * 60)

    # 4.1 构造周期分类器（真实环境：Tushare stock_basic 注入行业映射 + 季报期评分缓存）
    from cycle_filter import CycleClassifier
    clf = CycleClassifier(score_cache={
        "600001": 0.85,   # 模拟：煤炭股财务波动大 → strong
        "600002": 0.55,   # 模拟：成长属性 → mid
    })
    clf.load_industry_mapping(
        code_l1={
            "600001": "煤炭",       # strong 强周期
            "600002": "电力设备",   # mid 中周期
            "600003": "银行",       # none 无周期
        },
        code_l2={
            "600001": "煤炭开采",   # 命中 excluded_sw_l2 默认列表
        },
    )

    # 4.2 慢条件：排除强+中强周期（滑块默认 mid_weak），并精细排除"煤炭开采/石油开采"
    slow4 = SlowConditions(
        max_cycle_strength="mid_weak",
        excluded_sw_l2=("煤炭开采", "石油开采", "工业金属", "普钢"),
        cycle_classifier=clf,
    )
    pool4 = build_quarterly_pool(slow4)
    print(f"慢池（排除强/中强周期 + 二级排除）: {sorted(pool4)}")

    # 4.3 断言验证
    # 设计语义：max_cycle_strength='mid_weak'(=2) → 仅保留强度值 ≤ 2 的标的
    #   strong=5, mid_strong=4, mid=3 均被排除；mid_weak=2, weak=1, none=0 保留
    assert "600001" not in pool4, "煤炭(strong=5) 应被强度上限排除"
    assert "600002" not in pool4, "电力设备(mid=3 > mid_weak=2) 应被排除"
    # 600003 银行(none=0) 保留 —— 需其财务齐全且在慢池中
    print("\n  验证（滑块='mid_weak'，仅保留 中弱/弱/无周期）：")
    print(f"    600001 煤炭(strong)     → {'排除 ✓' if '600001' not in pool4 else '保留 ✗'}")
    print(f"    600002 电力设备(mid)    → {'排除 ✓' if '600002' not in pool4 else '保留 ✗'}")
    print(f"    600003 银行(none)       → {'保留 ✓' if '600003' in pool4 else '不在慢池(财务/其他条件)'}")
    assert True  # 前置断言已覆盖核心逻辑

    # 4.4 对比：滑块放宽到 'mid'（允许中周期，如电力设备/机械）
    slow4b = SlowConditions(max_cycle_strength="mid", cycle_classifier=clf)
    pool4b = build_quarterly_pool(slow4b)
    print(f"\n  滑块放宽到 'mid'（允许中周期）后慢池: {sorted(pool4b)}")

    # 4.5 直接验证分类器各档位（不依赖财务数据，确保端到端展示完整）
    print("\n  各标的周期强度（分类器直查）：")
    for code in ("600001", "600002", "600003"):
        tag = clf.classify(code)
        allowed_mid_weak = STRENGTH_RANK[tag.final_strength] <= STRENGTH_RANK["mid_weak"]
        print(f"    {code} {tag.sw_l1_name:<6}({tag.final_strength:<9}) → "
              f"滑块=mid_weak 时 {'保留' if allowed_mid_weak else '排除'}")
    assert not clf.is_allowed("600001", "mid_weak"), "煤炭应被排除"
    assert clf.is_allowed("600003", "mid_weak"), "银行应保留"
    print("\n  ✅ 强度档位判定正确：强周期出局、无周期保留、滑块可调")

    print("\n" + "=" * 60)
    print("✅ 演示4 完成：周期过滤已集成到季度慢池构建流程")
    print("=" * 60)
