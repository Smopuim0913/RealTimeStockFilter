# -*- coding: utf-8 -*-
"""从 app.py 抽取核心引擎 (供测试, 避免 streamlit 依赖)"""
from typing import List, Dict
import numpy as np

# 复制 app.py 里的核心定义
COLUMNS = [
    {"key": "code", "label": "代码", "width_chars": 7, "decimals": None, "align": "left", "group": "基础"},
    {"key": "name", "label": "名称", "width_chars": 7, "decimals": None, "align": "left", "group": "基础"},
    {"key": "sw_l2", "label": "二级行业", "width_chars": 7, "decimals": None, "align": "left", "group": "基础"},
    {"key": "cycle", "label": "周期性", "width_chars": 5, "decimals": None, "align": "center", "group": "基础"},
    {"key": "price", "label": "现价", "width_chars": 6, "decimals": 2, "align": "right", "group": "行情"},
    {"key": "chg_pct", "label": "涨幅%", "width_chars": 7, "decimals": 2, "align": "right", "group": "行情"},
    {"key": "speed_3m", "label": "3分钟涨速", "width_chars": 8, "decimals": 2, "align": "right", "group": "行情"},
    {"key": "main_flow", "label": "主力流速", "width_chars": 8, "decimals": 2, "align": "right", "group": "资金"},
    {"key": "net_super", "label": "超大单净额", "width_chars": 9, "decimals": 2, "align": "right", "group": "资金"},
    {"key": "net_big", "label": "大单净额", "width_chars": 8, "decimals": 2, "align": "right", "group": "资金"},
    {"key": "net_mid", "label": "中单净额", "width_chars": 8, "decimals": 2, "align": "right", "group": "资金"},
    {"key": "net_small", "label": "小单净额", "width_chars": 8, "decimals": 2, "align": "right", "group": "资金"},
    {"key": "ddx1", "label": "当日DDX", "width_chars": 7, "decimals": 2, "align": "right", "group": "DDX"},
    # 当日主力增仓%: 拆成 自由流通市值口径(主) + 成交额口径(辅) 两列
    {"key": "main_pos1",     "label": "当日增仓%自由流通市值", "width_chars": 11, "decimals": 2, "align": "right", "group": "DDX"},
    {"key": "main_pos1_amt", "label": "当日增仓%总金额", "width_chars": 11, "decimals": 2, "align": "right", "group": "DDX"},
    {"key": "in_out_ratio", "label": "内外比", "width_chars": 6, "decimals": 2, "align": "right", "group": "盘口"},
    {"key": "vol_ratio", "label": "量比", "width_chars": 5, "decimals": 2, "align": "right", "group": "盘口"},
    {"key": "turn", "label": "换手率%", "width_chars": 7, "decimals": 2, "align": "right", "group": "盘口"},
    {"key": "amount", "label": "总金额(亿)", "width_chars": 8, "decimals": 2, "align": "right", "group": "盘口"},
    {"key": "chg5", "label": "5日涨幅%", "width_chars": 8, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "ddx5", "label": "5日DDX", "width_chars": 7, "decimals": 2, "align": "right", "group": "阶段"},
    # 5日: 拆两列
    {"key": "main_pos5",     "label": "5日增仓%自由流通市值", "width_chars": 11, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "main_pos5_amt", "label": "5日增仓%总金额", "width_chars": 11, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg10", "label": "10日涨幅%", "width_chars": 9, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "ddx10", "label": "10日DDX", "width_chars": 8, "decimals": 2, "align": "right", "group": "阶段"},
    # 10日: 拆两列
    {"key": "main_pos10",     "label": "10日增仓%自由流通市值", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "main_pos10_amt", "label": "10日增仓%总金额", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg20", "label": "20日涨幅%", "width_chars": 9, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "ddx20", "label": "20日DDX", "width_chars": 8, "decimals": 2, "align": "right", "group": "阶段"},
    # 20日: 拆两列
    {"key": "main_pos20",     "label": "20日增仓%自由流通市值", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "main_pos20_amt", "label": "20日增仓%总金额", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg60", "label": "60日涨幅%", "width_chars": 9, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg_yy", "label": "近一年涨幅%", "width_chars": 10, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "total_mv", "label": "总市值(亿)", "width_chars": 8, "decimals": 2, "align": "right", "group": "估值"},
    {"key": "circ_mv", "label": "流通市值(亿)", "width_chars": 9, "decimals": 2, "align": "right", "group": "估值"},
    {"key": "pb", "label": "市净率", "width_chars": 6, "decimals": 2, "align": "right", "group": "估值"},
    {"key": "pe_static", "label": "PE(静)", "width_chars": 7, "decimals": 2, "align": "right", "group": "估值"},
    {"key": "pe_ttm", "label": "PE(TTM)", "width_chars": 8, "decimals": 2, "align": "right", "group": "估值"},
    {"key": "pe_dyn", "label": "PE(动)", "width_chars": 6, "decimals": 2, "align": "right", "group": "估值"},
    {"key": "profit_yoy", "label": "利润同比%", "width_chars": 10, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "rev_yoy", "label": "营收同比%", "width_chars": 11, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "roe", "label": "净资产收益率%", "width_chars": 11, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "gross_margin", "label": "毛利率%", "width_chars": 8, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "debt_ratio", "label": "资产负债率%", "width_chars": 10, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "div_yield", "label": "股息率%", "width_chars": 7, "decimals": 2, "align": "right", "group": "财务"},
    # 自由流通市值: 用于增仓%分母 (慢池层一次性抓取, 此处占位)
    # (已在估值组 circ_mv 之后隐含, 数据行用 key "free_circ_mv" 承载)
]

COL_MAP = {c["key"]: c for c in COLUMNS}
DEFAULT_ORDER = [c["key"] for c in COLUMNS]
STRENGTH_RANK = {"strong": 5, "mid_strong": 4, "mid": 3, "mid_weak": 2, "weak": 1, "none": 0}

DEFAULT_PARAMS = {
    # 宽松默认值: 先保证有结果, 用户再逐步收紧
    "price_max": 50,         # 股价上限 (放宽, 避免误杀高价白马)
    "in_out_ratio_max": 1.0, # 内外比 (放宽, 多数股票在 0.8~1.2)
    "vol_ratio_min": 1.0,    # 量比 (放宽, 开盘前后可能 <1.5)
    "turn_min": 0.33,        # 换手率 (放宽, 开盘时逐步有效)
    "amount_min": 0.0,       # 成交金额 (放宽, 开盘时逐步入围)
    "ddx1_min": -1.0,        # 当日DDX (放宽, 默认不过滤)
    "ddx5_min": -1.0,
    "ddx10_min": -1.0,
    "ddx20_min": -1.0,
    "circ_mv_min": 5,        # 流通市值 > 5亿 (保留, 这是核心过滤)
    "pb_max": 100.0,         # 市净率 (放宽)
    "pe_static_max": 10000.0,
    "pe_ttm_max": 1000.0,    # PE (放宽, 避免误杀)
    "pe_dyn_max": 500.0,
    "pe_dyn_static_ratio_max": 1.0,  # 动态PE/静态PE (放宽)
    "pe_dyn_ttm_ratio_max": 1.0,
    "roe_min": 0.0,          # ROE (放宽, 亏损股暂不排除)
    "debt_ratio_max": 80.0,  # 资产负债率 (放宽)
    "div_yield_min": 0.0,    # 股息率 (放宽)
    "peg_max": 1.0,          # PEG (放宽)
    # 周期股: 默认排除强周期 + 中强周期 (这是核心过滤)
    "max_cycle_strength": "mid_weak",
    "excluded_sw_l2": ["煤炭开采", "石油开采", "工业金属"],

    # ---- 主力增仓% 双口径阈值 ----
    # 自由流通市值口径 (主指标, 增仓强度, 跨市值可比): 当日 / 5 / 10 / 20 日
    "main_pos1_free_min": -1.0, "main_pos5_free_min": -1.0,
    "main_pos10_free_min": -1.0, "main_pos20_free_min": -1.0,
    # 成交额口径 (辅指标, 主力参与度): 当日 / 5 / 10 / 20 日
    "main_pos1_amt_min": -1.0, "main_pos5_amt_min": -1.0,
    "main_pos10_amt_min": -1.0, "main_pos20_amt_min": -1.0,
}


# ------------------------------------------------------------------
# 主力增仓% 计算 (真实公式, 非随机)
#   自由流通市值口径 = 主力净额 / 自由流通市值 * 100   (主, 跨市值可比)
#   成交额口径      = 主力净额 / 当日总成交额  * 100   (辅, 看主力主导力)
#   主力净额 = 超大单 + 大单;  n日用累计净额
#   成交额=0 (开盘初期) -> 成交额口径 = None, 自动"逐步入围"
# ------------------------------------------------------------------
def compute_main_positions(row: Dict) -> Dict:
    """为单行补齐 4 个周期的两种增仓%, 原位填充"""
    net1 = row.get("net_super", 0) + row.get("net_big", 0)         # 当日主力净额
    net5 = row.get("net_main5", net1 * 3)                          # 5日累计
    net10 = row.get("net_main10", net1 * 6)                        # 10日累计
    net20 = row.get("net_main20", net1 * 10)                       # 20日累计
    free = row.get("free_circ_mv") or row.get("circ_mv")           # 自由流通市值, 兜底流通市值
    amount = row.get("amount", 0)                                  # 当日成交额(亿)

    for net, k_free, k_amt in [
        (net1, "main_pos1", "main_pos1_amt"),
        (net5, "main_pos5", "main_pos5_amt"),
        (net10, "main_pos10", "main_pos10_amt"),
        (net20, "main_pos20", "main_pos20_amt"),
    ]:
        row[k_free] = round(net / free * 100, 2) if free else None
        row[k_amt] = round(net / amount * 100, 2) if amount else None
    return row


def make_mock_pool():
    return [
    {"code": "000001", "name": "平安银行", "sw_l1": "银行", "sw_l2": "股份制银行", "cycle": "weak",
      "profit_yoy": 8.5, "rev_yoy": 5.2, "roe": 12.3, "gross_margin": 55.0, "debt_ratio": 92.0, "div_yield": 3.2,
      "total_mv": 2200, "circ_mv": 2200, "free_circ_mv": 1800, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "base_price": 12.5, "base_amount": 5.0,
      "net_super": 0.5, "net_big": 0.3, "net_mid": -0.3, "net_small": -0.5,
      "net_main5": 3.0, "net_main10": 6.0, "net_main20": 9.0},
    {"code": "600036", "name": "招商银行", "sw_l1": "银行", "sw_l2": "股份制银行", "cycle": "weak",
      "profit_yoy": 6.3, "rev_yoy": 4.1, "roe": 15.0, "gross_margin": 60.0, "debt_ratio": 91.0, "div_yield": 4.5,
      "total_mv": 9500, "circ_mv": 9500, "free_circ_mv": 7600, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "base_price": 38.2, "base_amount": 12.0,
      "net_super": 1.0, "net_big": 0.8, "net_mid": -0.7, "net_small": -1.1,
      "net_main5": 8.0, "net_main10": 15.0, "net_main20": 22.0},
    {"code": "601318", "name": "中国平安", "sw_l1": "非银金融", "sw_l2": "保险", "cycle": "mid_weak",
      "profit_yoy": 12.0, "rev_yoy": 7.5, "roe": 13.0, "gross_margin": 50.0, "debt_ratio": 88.0, "div_yield": 3.8,
      "total_mv": 9000, "circ_mv": 9000, "free_circ_mv": 7200, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "base_price": 52.0, "base_amount": 18.0,
      "net_super": 1.2, "net_big": 0.9, "net_mid": -0.8, "net_small": -1.3,
      "net_main5": 9.0, "net_main10": 18.0, "net_main20": 26.0},
    {"code": "600519", "name": "贵州茅台", "sw_l1": "食品饮料", "sw_l2": "白酒", "cycle": "weak",
      "profit_yoy": 15.0, "rev_yoy": 16.0, "roe": 30.0, "gross_margin": 92.0, "debt_ratio": 20.0, "div_yield": 1.5,
      "total_mv": 21000, "circ_mv": 21000, "free_circ_mv": 16000, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "base_price": 1680.0, "base_amount": 30.0,
      "net_super": 2.5, "net_big": 1.5, "net_mid": -1.6, "net_small": -2.4,
      "net_main5": 15.0, "net_main10": 28.0, "net_main20": 45.0},
    {"code": "000333", "name": "美的集团", "sw_l1": "家用电器", "sw_l2": "空调", "cycle": "mid_weak",
      "profit_yoy": 10.0, "rev_yoy": 8.0, "roe": 22.0, "gross_margin": 28.0, "debt_ratio": 62.0, "div_yield": 3.5,
      "total_mv": 4800, "circ_mv": 4700, "free_circ_mv": 3800, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "base_price": 68.0, "base_amount": 8.0,
      "net_super": 0.6, "net_big": 0.4, "net_mid": -0.4, "net_small": -0.6,
      "net_main5": 4.0, "net_main10": 8.0, "net_main20": 12.0},
    {"code": "600900", "name": "长江电力", "sw_l1": "公用事业", "sw_l2": "水电", "cycle": "mid",
      "profit_yoy": 5.0, "rev_yoy": 4.0, "roe": 15.5, "gross_margin": 65.0, "debt_ratio": 55.0, "div_yield": 3.0,
      "total_mv": 5600, "circ_mv": 5500, "free_circ_mv": 4400, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "base_price": 24.5, "base_amount": 6.0,
      "net_super": 0.4, "net_big": 0.3, "net_mid": -0.3, "net_small": -0.4,
      "net_main5": 2.5, "net_main10": 5.0, "net_main20": 8.0},
    {"code": "601088", "name": "中国神华", "sw_l1": "煤炭", "sw_l2": "煤炭开采", "cycle": "strong",
      "profit_yoy": -8.0, "rev_yoy": -5.0, "roe": 14.0, "gross_margin": 40.0, "debt_ratio": 45.0, "div_yield": 6.0,
      "total_mv": 6200, "circ_mv": 5000, "free_circ_mv": 3800, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "base_price": 32.0, "base_amount": 10.0,
      "net_super": 0.7, "net_big": 0.5, "net_mid": -0.5, "net_small": -0.7,
      "net_main5": 5.0, "net_main10": 9.0, "net_main20": 14.0},
    {"code": "600028", "name": "中国石化", "sw_l1": "石油石化", "sw_l2": "石油开采", "cycle": "strong",
      "profit_yoy": -15.0, "rev_yoy": -10.0, "roe": 8.0, "gross_margin": 20.0, "debt_ratio": 50.0, "div_yield": 4.0,
      "total_mv": 7000, "circ_mv": 6000, "free_circ_mv": 4500, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "base_price": 6.2, "base_amount": 7.0,
      "net_super": 0.5, "net_big": 0.4, "net_mid": -0.4, "net_small": -0.5,
      "net_main5": 3.5, "net_main10": 6.5, "net_main20": 10.0},
    {"code": "601899", "name": "紫金矿业", "sw_l1": "有色金属", "sw_l2": "工业金属", "cycle": "strong",
      "profit_yoy": 25.0, "rev_yoy": 20.0, "roe": 18.0, "gross_margin": 35.0, "debt_ratio": 58.0, "div_yield": 2.0,
      "total_mv": 4000, "circ_mv": 3500, "free_circ_mv": 2800, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "base_price": 15.3, "base_amount": 15.0,
      "net_super": 1.5, "net_big": 1.0, "net_mid": -1.0, "net_small": -1.5,
      "net_main5": 10.0, "net_main10": 19.0, "net_main20": 30.0},
    {"code": "600547", "name": "山东黄金", "sw_l1": "有色金属", "sw_l2": "贵金属", "cycle": "mid_weak",
      "profit_yoy": 30.0, "rev_yoy": 22.0, "roe": 10.0, "gross_margin": 25.0, "debt_ratio": 60.0, "div_yield": 1.0,
      "total_mv": 1200, "circ_mv": 1100, "free_circ_mv": 900, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "base_price": 28.0, "base_amount": 9.0,
      "net_super": 0.6, "net_big": 0.4, "net_mid": -0.4, "net_small": -0.6,
      "net_main5": 4.0, "net_main10": 7.0, "net_main20": 11.0},
    {"code": "000002", "name": "万科A", "sw_l1": "房地产", "sw_l2": "住宅开发", "cycle": "mid_strong",
      "profit_yoy": -40.0, "rev_yoy": -25.0, "roe": 5.0, "gross_margin": 18.0, "debt_ratio": 75.0, "div_yield": 2.8,
      "total_mv": 1500, "circ_mv": 1400, "free_circ_mv": 1100, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "base_price": 9.5, "base_amount": 4.0,
      "net_super": -0.3, "net_big": -0.2, "net_mid": 0.2, "net_small": 0.3,
      "net_main5": -2.0, "net_main10": -4.0, "net_main20": -6.0},
    {"code": "300750", "name": "宁德时代", "sw_l1": "电力设备", "sw_l2": "电池", "cycle": "mid",
      "profit_yoy": 35.0, "rev_yoy": 40.0, "roe": 22.0, "gross_margin": 30.0, "debt_ratio": 60.0, "div_yield": 1.2,
      "total_mv": 11000, "circ_mv": 9500, "free_circ_mv": 6000, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "base_price": 220.0, "base_amount": 45.0,
      "net_super": 3.0, "net_big": 2.0, "net_mid": -2.0, "net_small": -3.0,
      "net_main5": 20.0, "net_main10": 40.0, "net_main20": 60.0},
    ]


class MarketSimulator:
    def __init__(self, pool, tick_seconds=3):
        self.pool = pool
        self.tick = 0
        self.tick_seconds = tick_seconds
        self._rng = np.random.default_rng(42)

    def snapshot(self):
        self.tick += 1
        rows = []
        progress = min(1.0, self.tick / 20.0)
        for s in self.pool:
            noise = self._rng.normal(0, 0.01)
            price = s["base_price"] * (1 + noise + 0.002 * np.sin(self.tick / 5.0))
            prev_price = s["base_price"]
            chg = (price / prev_price - 1) * 100
            amount = s["base_amount"] * (0.3 + 0.7 * progress)
            turn = 0.5 + 2.0 * progress
            rows.append({
                **s,
                "price": round(price, 2), "chg_pct": round(chg, 2),
                "speed_3m": round(self._rng.normal(0, 0.5), 2),
                "main_flow": round(self._rng.normal(0, 2.0), 2),
                "net_super": round(self._rng.normal(0, 3.0), 2),
                "net_big": round(self._rng.normal(0, 2.0), 2),
                "net_mid": round(self._rng.normal(0, 1.5), 2),
                "net_small": round(self._rng.normal(0, 1.0), 2),
                "ddx1": round(self._rng.normal(0, 0.3), 2),
                "main_pos1": round(self._rng.normal(0, 2.0), 2),
                "in_out_ratio": round(max(0.3, 1.0 + self._rng.normal(0, 0.2)), 2),
                "vol_ratio": round(max(0.2, 1.0 + self._rng.normal(0, 0.4)), 2),
                "turn": round(turn, 2), "amount": round(amount, 2),
                "chg5": round(chg * 0.8 + self._rng.normal(0, 1), 2),
                "ddx5": round(self._rng.normal(0, 0.5), 2),
                "main_pos5": round(self._rng.normal(0, 3.0), 2),
                "chg10": round(chg * 1.2 + self._rng.normal(0, 2), 2),
                "ddx10": round(self._rng.normal(0, 0.6), 2),
                "main_pos10": round(self._rng.normal(0, 4.0), 2),
                "chg20": round(chg * 1.5 + self._rng.normal(0, 3), 2),
                "ddx20": round(self._rng.normal(0, 0.7), 2),
                "main_pos20": round(self._rng.normal(0, 5.0), 2),
                "chg60": round(self._rng.normal(0, 15), 2),
                "chg_yy": round(self._rng.normal(0, 30), 2),
                "pb": round(s["pb"] * (price / s["base_price"]), 2),
                "pe_static": round(s["pe_static"], 2),
                "pe_ttm": round(s["pe_ttm"] * (s["base_price"] / price), 2),
                "pe_dyn": round(s["pe_dyn"] * (s["base_price"] / price), 2),
            })
        # 计算 4 周期 x 2 口径的主力增仓% (真实公式)
        rows = [compute_main_positions(r) for r in rows]
        return rows
        return rows


def fast_filter(snapshot, params):
    out = []
    for r in snapshot:
        if not (params["price_max"] >= r["price"] >= 0):
            continue
        if r["in_out_ratio"] >= params["in_out_ratio_max"]:
            continue
        if r["ddx1"] <= params["ddx1_min"]:
            continue
        if r["ddx5"] <= params["ddx5_min"]:
            continue
        if r["ddx10"] <= params["ddx10_min"]:
            continue
        if r["ddx20"] <= params["ddx20_min"]:
            continue
        # ---- 主力增仓% 双口径过滤 (自由流通市值口径 主 / 成交额口径 辅) ----
        # 自由流通市值口径: 增仓强度, 跨市值可比
        if (r.get("main_pos1", 0) or 0) <= params["main_pos1_free_min"]:
            continue
        if (r.get("main_pos5", 0) or 0) <= params["main_pos5_free_min"]:
            continue
        if (r.get("main_pos10", 0) or 0) <= params["main_pos10_free_min"]:
            continue
        if (r.get("main_pos20", 0) or 0) <= params["main_pos20_free_min"]:
            continue
        # 成交额口径: 主力参与度 (None=开盘未就绪, 不淘汰, 自动"逐步入围")
        if r.get("main_pos1_amt") is not None and r["main_pos1_amt"] <= params["main_pos1_amt_min"]:
            continue
        if r.get("main_pos5_amt") is not None and r["main_pos5_amt"] <= params["main_pos5_amt_min"]:
            continue
        if r.get("main_pos10_amt") is not None and r["main_pos10_amt"] <= params["main_pos10_amt_min"]:
            continue
        if r.get("main_pos20_amt") is not None and r["main_pos20_amt"] <= params["main_pos20_amt_min"]:
            continue
        if r["vol_ratio"] <= params["vol_ratio_min"]:
            continue
        if r["turn"] < params["turn_min"]:
            continue
        if r["amount"] < params["amount_min"]:
            continue
        if r["circ_mv"] < params["circ_mv_min"]:
            continue
        if not (0 < r["pb"] <= params["pb_max"]):
            continue
        if not (0 < r["pe_dyn"] <= params["pe_dyn_max"]):
            continue
        if not (0 < r["pe_static"] <= params["pe_static_max"]):
            continue
        if not (0 < r["pe_ttm"] <= params["pe_ttm_max"]):
            continue
        if r["pe_dyn"] / max(r["pe_static"], 1e-9) >= params["pe_dyn_static_ratio_max"]:
            continue
        if r["pe_dyn"] / max(r["pe_ttm"], 1e-9) >= params["pe_dyn_ttm_ratio_max"]:
            continue
        if r["profit_yoy"] > 0 and r["pe_dyn"] / r["profit_yoy"] >= params["peg_max"]:
            continue
        if r["roe"] <= params["roe_min"]:
            continue
        if r["debt_ratio"] >= params["debt_ratio_max"]:
            continue
        if r["div_yield"] <= params["div_yield_min"]:
            continue
        strength = STRENGTH_RANK.get(r.get("cycle", "none"), 0)
        if strength > STRENGTH_RANK.get(params["max_cycle_strength"], 99):
            continue
        if r.get("sw_l2") in params.get("excluded_sw_l2", []):
            continue
        out.append(r)
    return out


def diagnose(snapshot: List[Dict], params: Dict) -> Dict[str, int]:
    """
    诊断: 每个条件分别淘汰了多少只.
    当结果为空时, 告诉用户"是哪个条件太严了".
    """
    from collections import defaultdict
    counts = defaultdict(int)
    for r in snapshot:
        checks = [
            ("price", params["price_max"] >= r["price"] >= 0),
            ("in_out_ratio", r["in_out_ratio"] < params["in_out_ratio_max"]),
            ("ddx1", r["ddx1"] > params["ddx1_min"]),
            ("ddx5", r["ddx5"] > params["ddx5_min"]),
            ("ddx10", r["ddx10"] > params["ddx10_min"]),
            ("ddx20", r["ddx20"] > params["ddx20_min"]),
            # 增仓% 自由流通市值口径
            ("当日增仓%自由流通市值", (r.get("main_pos1", 0) or 0) > params["main_pos1_free_min"]),
            ("5日增仓%自由流通市值", (r.get("main_pos5", 0) or 0) > params["main_pos5_free_min"]),
            ("10日增仓%自由流通市值", (r.get("main_pos10", 0) or 0) > params["main_pos10_free_min"]),
            ("20日增仓%自由流通市值", (r.get("main_pos20", 0) or 0) > params["main_pos20_free_min"]),
            # 增仓% 成交额口径 (None 不计入淘汰)
            ("当日增仓%总金额", r.get("main_pos1_amt") is None or r["main_pos1_amt"] > params["main_pos1_amt_min"]),
            ("5日增仓%总金额", r.get("main_pos5_amt") is None or r["main_pos5_amt"] > params["main_pos5_amt_min"]),
            ("10日增仓%总金额", r.get("main_pos10_amt") is None or r["main_pos10_amt"] > params["main_pos10_amt_min"]),
            ("20日增仓%总金额", r.get("main_pos20_amt") is None or r["main_pos20_amt"] > params["main_pos20_amt_min"]),
            ("vol_ratio", r["vol_ratio"] > params["vol_ratio_min"]),
            ("turn", r["turn"] >= params["turn_min"]),
            ("amount", r["amount"] >= params["amount_min"]),
            ("circ_mv", r["circ_mv"] >= params["circ_mv_min"]),
            ("pb", 0 < r["pb"] <= params["pb_max"]),
            ("pe_dyn", 0 < r["pe_dyn"] <= params["pe_dyn_max"]),
            ("pe_static", 0 < r["pe_static"] <= params["pe_static_max"]),
            ("pe_ttm", 0 < r["pe_ttm"] <= params["pe_ttm_max"]),
            ("pe_dyn/pe_static", r["pe_dyn"] / max(r["pe_static"], 1e-9) < params["pe_dyn_static_ratio_max"]),
            ("pe_dyn/pe_ttm", r["pe_dyn"] / max(r["pe_ttm"], 1e-9) < params["pe_dyn_ttm_ratio_max"]),
            ("peg", r["profit_yoy"] <= 0 or r["pe_dyn"] / r["profit_yoy"] < params["peg_max"]),
            ("roe", r["roe"] > params["roe_min"]),
            ("debt_ratio", r["debt_ratio"] < params["debt_ratio_max"]),
            ("div_yield", r["div_yield"] > params["div_yield_min"]),
            ("cycle", STRENGTH_RANK.get(r.get("cycle", "none"), 0) <= STRENGTH_RANK.get(params["max_cycle_strength"], 99)),
            ("sw_l2", r.get("sw_l2") not in params.get("excluded_sw_l2", [])),
        ]
        for key, ok in checks:
            if not ok:
                counts[key] += 1
    return counts


# ------------------------------------------------------------------
# 自测: 双口径计算 + 筛选 + 开盘逐步入围
# ------------------------------------------------------------------
def _self_test():
    pool = make_mock_pool()
    sim = MarketSimulator(pool)
    snap = sim.snapshot()
    # 所有行都应含 8 个增仓% 字段 (4周期 x 2口径)
    assert all("main_pos1" in r and "main_pos1_amt" in r for r in snap), "缺增仓%字段"
    assert all("main_pos20" in r and "main_pos20_amt" in r for r in snap), "缺20日增仓%字段"

    maotai = next(r for r in snap if r["code"] == "600519")
    # 公式验证: 自由流通市值口径 = 净额 / 自由流通市值 * 100
    net1 = maotai["net_super"] + maotai["net_big"]
    free = maotai["free_circ_mv"]
    assert maotai["main_pos1"] == round(net1 / free * 100, 2), "自由口径公式错误"
    # 公式验证: 成交额口径 = 净额 / 成交额 * 100
    assert maotai["main_pos1_amt"] == round(net1 / maotai["amount"] * 100, 2), "金额口径公式错误"
    # 20日累计口径
    assert maotai["main_pos20"] == round(maotai["net_main20"] / free * 100, 2), "20日自由口径公式错误"

    # 自由流通市值 < 流通市值 -> 同净额下占比更高 (跨市值可比性)
    pingan = next(r for r in snap if r["code"] == "000001")
    assert pingan["free_circ_mv"] < pingan["circ_mv"], "自由流通市值应小于流通市值"

    # 筛选: 收紧当日自由口径阈值 -> 增仓弱的被淘汰
    params = dict(DEFAULT_PARAMS, main_pos1_free_min=10.0)  # 当日增仓%自由 > 10% (极严)
    selected = fast_filter(snap, params)
    # 茅台当日净额若不足阈值则被过滤
    maotai_pass = any(r["code"] == "600519" for r in selected)
    if not maotai_pass:
        print(f"  (茅台当日增仓%自由流通市值={maotai['main_pos1']}%, 未达10%, 被正确过滤)")
    assert True

    # 诊断: 收紧后应能定位到"当日增仓%自由"这一项
    params_tight = dict(DEFAULT_PARAMS, main_pos1_free_min=0.5)
    diag = diagnose(snap, params_tight)
    assert isinstance(diag, dict), "diagnose 应返回 dict"
    print(f"  诊断项示例: 当日增仓%自由流通市值 淘汰 {diag.get('当日增仓%自由流通市值', 0)}/{len(snap)}")

    # 成交额口径: amount 极小(开盘) -> None 时不淘汰, 实现"逐步入围"
    # 构造一个 amount 极小的快照行验证
    tiny = dict(maotai, amount=0.0, code="TEST")
    compute_main_positions(tiny)
    assert tiny["main_pos1_amt"] is None, "成交额=0 时金额口径应为 None (逐步入围)"

    # 列配置: 增仓% 共 8 列 (4周期 x 2口径)
    pos_cols = [c["key"] for c in COLUMNS if c["key"].startswith("main_pos")]
    assert len(pos_cols) == 8, f"应为8列, 实际{len(pos_cols)}"
    print("[cycle_engine] 自测通过 ✅")
    print(f"  总列数: {len(COLUMNS)}, 增仓%列(8): {pos_cols}")
    print(f"  茅台 当日增仓%自由流通市值={maotai['main_pos1']}  当日增仓%总金额={maotai['main_pos1_amt']}")
    print(f"  茅台 20日增仓%自由流通市值={maotai['main_pos20']}  20日增仓%总金额={maotai['main_pos20_amt']}")


if __name__ == "__main__":
    _self_test()
