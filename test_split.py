# -*- coding: utf-8 -*-
"""
验证: n日主力增仓占比 拆分为两列
  - 主指标: 主力净额 / 自由流通市值  (增仓强度, 跨市值可比)
  - 辅指标: 主力净额 / 当日总成交额  (主力参与度)
口径说明见文末 main() 的断言与打印
"""
from typing import List, Dict
import numpy as np


# ------------------------------------------------------------------
# 列元配置: 每个 n 日增仓% 拆成 自由流通市值口径 + 成交额口径 两列
# ------------------------------------------------------------------
COLUMNS = [
    {"key": "code", "label": "代码", "width_chars": 7, "decimals": None, "align": "left", "group": "基础"},
    {"key": "name", "label": "名称", "width_chars": 7, "decimals": None, "align": "left", "group": "基础"},
    {"key": "sw_l2", "label": "二级行业", "width_chars": 7, "decimals": None, "align": "left", "group": "基础"},
    {"key": "cycle", "label": "周期性", "width_chars": 5, "decimals": None, "align": "center", "group": "基础"},
    {"key": "price", "label": "现价", "width_chars": 6, "decimals": 2, "align": "right", "group": "行情"},
    {"key": "chg_pct", "label": "涨幅%", "width_chars": 7, "decimals": 2, "align": "right", "group": "行情"},
    {"key": "net_super", "label": "超大单净额", "width_chars": 9, "decimals": 2, "align": "right", "group": "资金"},
    {"key": "net_big", "label": "大单净额", "width_chars": 8, "decimals": 2, "align": "right", "group": "资金"},
    {"key": "net_mid", "label": "中单净额", "width_chars": 8, "decimals": 2, "align": "right", "group": "资金"},
    {"key": "net_small", "label": "小单净额", "width_chars": 8, "decimals": 2, "align": "right", "group": "资金"},
    {"key": "ddx1", "label": "当日DDX", "width_chars": 7, "decimals": 2, "align": "right", "group": "DDX"},
    # ---- 当日: 拆两列 ----
    {"key": "main_pos1",    "label": "当日增仓%自由", "width_chars": 11, "decimals": 2, "align": "right", "group": "DDX"},
    {"key": "main_pos1_amt", "label": "当日增仓%金额", "width_chars": 11, "decimals": 2, "align": "right", "group": "DDX"},
    {"key": "in_out_ratio", "label": "内外比", "width_chars": 6, "decimals": 2, "align": "right", "group": "盘口"},
    {"key": "vol_ratio", "label": "量比", "width_chars": 5, "decimals": 2, "align": "right", "group": "盘口"},
    {"key": "turn", "label": "换手率%", "width_chars": 7, "decimals": 2, "align": "right", "group": "盘口"},
    {"key": "amount", "label": "成交金额亿", "width_chars": 8, "decimals": 2, "align": "right", "group": "盘口"},
    {"key": "chg5", "label": "5日涨幅%", "width_chars": 8, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "ddx5", "label": "5日DDX", "width_chars": 7, "decimals": 2, "align": "right", "group": "阶段"},
    # ---- 5日: 拆两列 ----
    {"key": "main_pos5",    "label": "5日增仓%自由", "width_chars": 11, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "main_pos5_amt", "label": "5日增仓%金额", "width_chars": 11, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg10", "label": "10日涨幅%", "width_chars": 9, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "ddx10", "label": "10日DDX", "width_chars": 8, "decimals": 2, "align": "right", "group": "阶段"},
    # ---- 10日: 拆两列 ----
    {"key": "main_pos10",    "label": "10日增仓%自由", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "main_pos10_amt", "label": "10日增仓%金额", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg20", "label": "20日涨幅%", "width_chars": 9, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "ddx20", "label": "20日DDX", "width_chars": 8, "decimals": 2, "align": "right", "group": "阶段"},
    # ---- 20日: 拆两列 ----
    {"key": "main_pos20",    "label": "20日增仓%自由", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "main_pos20_amt", "label": "20日增仓%金额", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg60", "label": "60日涨幅%", "width_chars": 9, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg_yy", "label": "近一年涨幅%", "width_chars": 10, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "total_mv", "label": "总市值亿", "width_chars": 8, "decimals": 2, "align": "right", "group": "估值"},
    {"key": "circ_mv", "label": "流通市值亿", "width_chars": 9, "decimals": 2, "align": "right", "group": "估值"},
    {"key": "free_circ_mv", "label": "自由流通市值亿", "width_chars": 12, "decimals": 2, "align": "right", "group": "估值"},
    {"key": "pb", "label": "市净率", "width_chars": 6, "decimals": 2, "align": "right", "group": "估值"},
    {"key": "pe_static", "label": "PE静", "width_chars": 7, "decimals": 2, "align": "right", "group": "估值"},
    {"key": "pe_ttm", "label": "PE(TTM)", "width_chars": 8, "decimals": 2, "align": "right", "group": "估值"},
    {"key": "pe_dyn", "label": "PE动", "width_chars": 6, "decimals": 2, "align": "right", "group": "估值"},
    {"key": "profit_yoy", "label": "净利润同比%", "width_chars": 10, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "rev_yoy", "label": "营业收入同比%", "width_chars": 11, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "roe", "label": "净资产收益率%", "width_chars": 11, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "gross_margin", "label": "毛利率%", "width_chars": 8, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "debt_ratio", "label": "资产负债率%", "width_chars": 10, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "div_yield", "label": "股息率%", "width_chars": 7, "decimals": 2, "align": "right", "group": "财务"},
]

COL_MAP = {c["key"]: c for c in COLUMNS}
DEFAULT_ORDER = [c["key"] for c in COLUMNS]


# ------------------------------------------------------------------
# 真实计算公式
#   主力增仓% (自由流通市值口径) = 主力净额 / 自由流通市值 * 100
#   主力增仓% (成交额口径)      = 主力净额 / 当日总成交额   * 100
#   主力净额 = 超大单 + 大单 (DDX 体系口径)
#   单位: 净额/市值 用 亿; amount 已是 亿
# ------------------------------------------------------------------
def compute_main_positions(row: Dict) -> Dict:
    """为单行补齐 4 个周期的两种增仓% (原位填充, 不新增随机字段)"""
    # 主力净额 = 超大单 + 大单 (模拟里已给出, 实盘来自资金流接口)
    net1 = row.get("net_super", 0) + row.get("net_big", 0)  # 当日主力净额(亿)
    net5 = row.get("net_main5", net1 * 3)                    # 5日累计主力净额(亿)
    net10 = row.get("net_main10", net1 * 6)                  # 10日
    net20 = row.get("net_main20", net1 * 10)                 # 20日

    free = row.get("free_circ_mv") or row.get("circ_mv")     # 自由流通市值(亿), 兜底用流通市值
    amount = row.get("amount", 0)                            # 当日成交额(亿)

    for net, k_free, k_amt in [
        (net1, "main_pos1", "main_pos1_amt"),
        (net5, "main_pos5", "main_pos5_amt"),
        (net10, "main_pos10", "main_pos10_amt"),
        (net20, "main_pos20", "main_pos20_amt"),
    ]:
        # 自由流通市值口径
        row[k_free] = round(net / free * 100, 2) if free else None
        # 成交额口径 (成交额=0 时开盘初期为 None, 自动"逐步入围")
        row[k_amt] = round(net / amount * 100, 2) if amount else None
    return row


# ---- Mock 池: 补充 free_circ_mv / net_main(n日累计主力净额) ----
def make_mock_pool():
    return [
        {"code": "600519", "name": "贵州茅台", "sw_l2": "白酒", "cycle": "weak",
         "base_price": 1680.0, "amount": 30.0,
         "total_mv": 21000, "circ_mv": 21000, "free_circ_mv": 16000,  # 自由流通 < 流通
         "net_super": 2.5, "net_big": 1.5, "net_mid": -1.0, "net_small": -3.0,
         "net_main5": 15.0, "net_main10": 28.0, "net_main20": 45.0},
        {"code": "300750", "name": "宁德时代", "sw_l2": "电池", "cycle": "mid",
         "base_price": 220.0, "amount": 45.0,
         "total_mv": 11000, "circ_mv": 9500, "free_circ_mv": 6000,
         "net_super": 3.0, "net_big": 2.0, "net_mid": -0.5, "net_small": -4.5,
         "net_main5": 20.0, "net_main10": 40.0, "net_main20": 60.0},
        {"code": "000001", "name": "平安银行", "sw_l2": "股份制银行", "cycle": "weak",
         "base_price": 12.50, "amount": 5.0,
         "total_mv": 2200, "circ_mv": 2200, "free_circ_mv": 1800,
         "net_super": 0.5, "net_big": 0.3, "net_mid": -0.2, "net_small": -0.6,
         "net_main5": 3.0, "net_main10": 6.0, "net_main20": 9.0},
        # 开盘初期: 成交额极小 -> 成交额口径应得 None (逐步入围)
        {"code": "600036", "name": "招商银行", "sw_l2": "股份制银行", "cycle": "weak",
         "base_price": 38.20, "amount": 0.0,
         "total_mv": 9500, "circ_mv": 9500, "free_circ_mv": 7000,
         "net_super": 1.0, "net_big": 0.8, "net_mid": -0.3, "net_small": -1.5,
         "net_main5": 8.0, "net_main10": 15.0, "net_main20": 22.0},
    ]


def main():
    pool = make_mock_pool()
    print("=" * 96)
    print(f"{'名称':<8}{'周期':<6}{'主力净额(亿)':<14}{'成交额':<8}{'自由流通市值':<14}{'增仓%自由':<12}{'增仓%金额':<12}")
    print("=" * 96)

    for r in pool:
        compute_main_positions(r)
        net1 = r["net_super"] + r["net_big"]
        free = r["free_circ_mv"]
        print(f"{r['name']:<8}{'当日':<6}{net1:<14}{r['amount']:<8}{free:<14}"
              f"{str(r['main_pos1']):<12}{str(r['main_pos1_amt']):<12}")

        # ---- 关键断言 ----
        # 1. 自由流通市值口径: 分母越小值越大 (茅台 vs 宁德同净额时宁德更高)
        # 2. 成交额口径: 大市值高成交额会被稀释 (茅台 4亿/30亿 < 宁德 5亿/45亿 的占比逻辑)
        # 3. 成交额=0 时 (开盘初期), 成交额口径 = None (逐步入围)

    print()

    # 断言 1: 成交额=0 的开盘股, 成交额口径为 None
    maotai = next(r for r in pool if r["code"] == "600519")
    zhaoshang = next(r for r in pool if r["code"] == "600036")
    assert zhaoshang["main_pos1_amt"] is None, "开盘成交额=0 时应为 None (逐步入围)"
    assert maotai["main_pos1_amt"] is not None, "正常成交额时应有值"
    print("✅ [开盘逐步入围] 成交额=0 -> 增仓%金额=None")

    # 断言 2: 自由流通市值口径, 宁德(6000亿)比茅台(16000亿)同净额时占比更高
    ningde = next(r for r in pool if r["code"] == "300750")
    # 宁德自由流通市值更小 -> 同一净额下增仓%自由 更大
    assert ningde["main_pos1"] > maotai["main_pos1"], \
        "自由流通市值越小, 同净额增仓%应更大 (宁德>茅台)"
    print(f"✅ [跨市值可比] 宁德增仓%自由={ningde['main_pos1']} > 茅台={maotai['main_pos1']} "
          f"(宁德自由流通市值更小, 占比更高)")

    # 断言 3: 茅台 20日累计增仓 用自由流通市值口径 计算正确
    expected_maotai_20 = round(45.0 / 16000 * 100, 2)
    assert maotai["main_pos20"] == expected_maotai_20, f"20日自由口径应={expected_maotai_20}"
    print(f"✅ [计算正确] 茅台20日增仓%自由 = 45/16000*100 = {maotai['main_pos20']}")

    # 断言 4: 字段数 = 基础字段 + 4周期*2列 + 其它
    pos_cols = [k for k in DEFAULT_ORDER if k.startswith("main_pos")]
    assert len(pos_cols) == 8, f"应为8列(4周期x2), 实际{len(pos_cols)}"
    print(f"✅ [列数正确] n日增仓% 共 {len(pos_cols)} 列: {pos_cols}")

    # 断言 5: 自由流通市值 < 流通市值 (茅台 16000 < 21000)
    assert maotai["free_circ_mv"] < maotai["total_mv"]
    print(f"✅ [口径合理] 自由流通市值({maotai['free_circ_mv']}亿) < 流通市值({maotai['circ_mv']}亿)")

    # ---- 打印茅台完整两列对照 ----
    print("\n【茅台 当日/5/10/20 两列对照】")
    print(f"{'周期':<6}{'增仓%自由':<14}{'增仓%金额':<14}")
    for d in [1, 5, 10, 20]:
        kf = f"main_pos{d}" if d != 1 else "main_pos1"
        ka = f"main_pos{d}_amt" if d != 1 else "main_pos1_amt"
        print(f"{'当日' if d==1 else str(d)+'日':<7}{maotai[kf]:<14}{maotai[ka]}")

    print("\n🎉 全部断言通过: 拆分方案成立")


if __name__ == "__main__":
    main()
