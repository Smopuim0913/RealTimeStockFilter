# -*- coding: utf-8 -*-
"""
九方智投风格 · 沪深京实时行情筛选器 (Streamlit 前端)

架构: 季度慢池(财报) + 盘中快筛(行情) + diff 自动进出
周期股过滤: 申万行业分级 + 周期性评分

运行:
    pip install streamlit pandas akshare
    streamlit run app.py

说明:
    本文件为「界面层」, 数据源使用内置 MOCK (实时轮询模拟).
    接实盘只需替换 data_source.py 里的 MOCK 为 akshare / tushare 调用即可,
    本文件无需改动.
"""

import time
from datetime import datetime
from typing import List, Dict, Optional

import numpy as np
import pandas as pd
import streamlit as st

# ------------------------------------------------------------------
# 1. 字段元配置 (决定: 列宽 / 小数位 / 对齐 / 格式化)
#    width_chars: 按字符数估算宽度 (中文/符号按1字符计)
#    decimals:    小数位数; None 表示整数
#    align:       left / right / center
# ------------------------------------------------------------------
COLUMNS: List[Dict] = [
    # 基础
    {"key": "code",        "label": "代码",   "width_chars": 7,  "decimals": None, "align": "left",   "group": "基础"},
    {"key": "name",        "label": "名称",   "width_chars": 7,  "decimals": None, "align": "left",   "group": "基础"},
    {"key": "sw_l2",       "label": "二级行业", "width_chars": 7, "decimals": None, "align": "left",  "group": "基础"},
    {"key": "cycle",       "label": "周期性",  "width_chars": 5,  "decimals": None, "align": "center", "group": "基础"},
    {"key": "price",       "label": "现价",   "width_chars": 6,  "decimals": 2,    "align": "right",  "group": "行情"},
    {"key": "chg_pct",     "label": "涨幅%",  "width_chars": 7,  "decimals": 2,    "align": "right",  "group": "行情"},
    {"key": "speed_3m",    "label": "3分钟涨速", "width_chars": 8, "decimals": 2,   "align": "right", "group": "行情"},
    {"key": "main_flow",   "label": "主力流速", "width_chars": 8,  "decimals": 2,   "align": "right", "group": "资金"},
    {"key": "net_super",   "label": "超大单净额", "width_chars": 9, "decimals": 2,  "align": "right", "group": "资金"},
    {"key": "net_big",     "label": "大单净额", "width_chars": 8,  "decimals": 2,   "align": "right", "group": "资金"},
    {"key": "net_mid",     "label": "中单净额", "width_chars": 8,  "decimals": 2,   "align": "right", "group": "资金"},
    {"key": "net_small",   "label": "小单净额", "width_chars": 8,  "decimals": 2,   "align": "right", "group": "资金"},
    {"key": "ddx1",        "label": "当日DDX", "width_chars": 7,  "decimals": 2,   "align": "right", "group": "DDX"},
    # 当日主力增仓%: 拆成 自由流通市值口径(主) + 成交额口径(辅) 两列
    {"key": "main_pos1",     "label": "当日增仓%自由", "width_chars": 11, "decimals": 2, "align": "right", "group": "DDX"},
    {"key": "main_pos1_amt", "label": "当日增仓%金额", "width_chars": 11, "decimals": 2, "align": "right", "group": "DDX"},
    {"key": "in_out_ratio","label": "内外比",  "width_chars": 6,  "decimals": 2,    "align": "right", "group": "盘口"},
    {"key": "vol_ratio",   "label": "量比",   "width_chars": 5,  "decimals": 2,    "align": "right", "group": "盘口"},
    {"key": "turn",        "label": "换手率%", "width_chars": 7,  "decimals": 2,    "align": "right", "group": "盘口"},
    {"key": "amount",      "label": "成交金额亿", "width_chars": 8, "decimals": 2,  "align": "right", "group": "盘口"},
    {"key": "chg5",        "label": "5日涨幅%", "width_chars": 8, "decimals": 2,   "align": "right", "group": "阶段"},
    {"key": "ddx5",        "label": "5日DDX",  "width_chars": 7,  "decimals": 2,   "align": "right", "group": "阶段"},
    # 5日: 拆两列
    {"key": "main_pos5",     "label": "5日增仓%自由", "width_chars": 11, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "main_pos5_amt", "label": "5日增仓%金额", "width_chars": 11, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg10",       "label": "10日涨幅%", "width_chars": 9, "decimals": 2,  "align": "right", "group": "阶段"},
    {"key": "ddx10",       "label": "10日DDX", "width_chars": 8,  "decimals": 2,   "align": "right", "group": "阶段"},
    # 10日: 拆两列
    {"key": "main_pos10",     "label": "10日增仓%自由", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "main_pos10_amt", "label": "10日增仓%金额", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg20",       "label": "20日涨幅%", "width_chars": 9, "decimals": 2,  "align": "right", "group": "阶段"},
    {"key": "ddx20",       "label": "20日DDX", "width_chars": 8,  "decimals": 2,   "align": "right", "group": "阶段"},
    # 20日: 拆两列
    {"key": "main_pos20",     "label": "20日增仓%自由", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "main_pos20_amt", "label": "20日增仓%金额", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg60",       "label": "60日涨幅%", "width_chars": 9, "decimals": 2,  "align": "right", "group": "阶段"},
    {"key": "chg_yy",      "label": "近一年涨幅%", "width_chars": 10, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "total_mv",    "label": "总市值亿", "width_chars": 8,  "decimals": 2,   "align": "right", "group": "估值"},
    {"key": "circ_mv",     "label": "流通市值亿", "width_chars": 9, "decimals": 2,  "align": "right", "group": "估值"},
    {"key": "pb",          "label": "市净率",  "width_chars": 6,  "decimals": 2,    "align": "right", "group": "估值"},
    {"key": "pe_static",   "label": "PE静",    "width_chars": 7,  "decimals": 2,    "align": "right", "group": "估值"},
    {"key": "pe_ttm",      "label": "PE(TTM)", "width_chars": 8,  "decimals": 2,    "align": "right", "group": "估值"},
    {"key": "pe_dyn",      "label": "PE动",    "width_chars": 6,  "decimals": 2,    "align": "right", "group": "估值"},
    {"key": "profit_yoy",  "label": "净利润同比%", "width_chars": 10, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "rev_yoy",     "label": "营业收入同比%", "width_chars": 11, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "roe",         "label": "净资产收益率%", "width_chars": 11, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "gross_margin","label": "毛利率%",  "width_chars": 8,  "decimals": 2,   "align": "right", "group": "财务"},
    {"key": "debt_ratio",  "label": "资产负债率%", "width_chars": 10, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "div_yield",   "label": "股息率%",  "width_chars": 7,  "decimals": 2,   "align": "right", "group": "财务"},
]

# 列 key -> config
COL_MAP = {c["key"]: c for c in COLUMNS}

# 默认列顺序 (可由用户拖动调整, 这里用 session_state 持久化)
DEFAULT_ORDER = [c["key"] for c in COLUMNS]


# ------------------------------------------------------------------
# 主力增仓% 计算 (真实公式, 非随机)
#   自由流通市值口径 = 主力净额 / 自由流通市值 * 100   (主, 跨市值可比)
#   成交额口径      = 主力净额 / 当日总成交额  * 100   (辅, 看主力主导力)
#   主力净额 = 超大单 + 大单;  n日用累计净额 net_mainN
#   成交额=0 (开盘初期) -> 成交额口径 = None, 自动"逐步入围"
# ------------------------------------------------------------------
def compute_main_positions(row: Dict) -> Dict:
    net1 = row.get("net_super", 0) + row.get("net_big", 0)
    net5 = row.get("net_main5", net1 * 3)
    net10 = row.get("net_main10", net1 * 6)
    net20 = row.get("net_main20", net1 * 10)
    free = row.get("free_circ_mv") or row.get("circ_mv")
    amount = row.get("amount", 0)
    for net, k_free, k_amt in [
        (net1, "main_pos1", "main_pos1_amt"),
        (net5, "main_pos5", "main_pos5_amt"),
        (net10, "main_pos10", "main_pos10_amt"),
        (net20, "main_pos20", "main_pos20_amt"),
    ]:
        row[k_free] = round(net / free * 100, 2) if free else None
        row[k_amt] = round(net / amount * 100, 2) if amount else None
    return row


# ------------------------------------------------------------------
# 2. MOCK 数据源 (替换 akshare/tushare 的地方)
# ------------------------------------------------------------------
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
    """模拟实时行情: 每轮在 base_price 附近随机游走, 金额随时间放大(模拟开盘->盘中)"""

    def __init__(self, pool: List[Dict], tick_seconds: int = 3):
        self.pool = pool
        self.tick = 0
        self.tick_seconds = tick_seconds
        self._rng = np.random.default_rng(42)

    def snapshot(self) -> List[Dict]:
        """生成一轮全市场快照 (对应 stock_zh_a_spot_em)"""
        self.tick += 1
        rows = []
        # progress: 0->1, 模拟开盘后成交金额逐步放大, 换手率逐步有效
        progress = min(1.0, self.tick / 20.0)

        for s in self.pool:
            noise = self._rng.normal(0, 0.01)
            price = s["base_price"] * (1 + noise + 0.002 * np.sin(self.tick / 5.0))
            prev_price = s["base_price"]
            chg = (price / prev_price - 1) * 100

            amount = s["base_amount"] * (0.3 + 0.7 * progress)  # 开盘小, 盘中放大
            turn = 0.5 + 2.0 * progress  # 换手率逐步有效

            rows.append({
                **s,
                "price": round(price, 2),
                "chg_pct": round(chg, 2),
                "speed_3m": round(self._rng.normal(0, 0.5), 2),
                "main_flow": round(self._rng.normal(0, 2.0), 2),
                "net_super": round(self._rng.normal(0, 3.0), 2),
                "net_big": round(self._rng.normal(0, 2.0), 2),
                "net_mid": round(self._rng.normal(0, 1.5), 2),
                "net_small": round(self._rng.normal(0, 1.0), 2),
                "ddx1": round(self._rng.normal(0, 0.3), 2),
                "in_out_ratio": round(max(0.3, 1.0 + self._rng.normal(0, 0.2)), 2),
                "vol_ratio": round(max(0.2, 1.0 + self._rng.normal(0, 0.4)), 2),
                "turn": round(turn, 2),
                "amount": round(amount, 2),
                # 阶段涨幅
                "chg5": round(chg * 0.8 + self._rng.normal(0, 1), 2),
                "ddx5": round(self._rng.normal(0, 0.5), 2),
                # 累计主力净额 (n日), 由 base 按比例派生, 叠加小幅波动
                "net_main5": round(s["net_main5"] * (0.9 + 0.2 * self._rng.random()), 2),
                "net_main10": round(s["net_main10"] * (0.9 + 0.2 * self._rng.random()), 2),
                "net_main20": round(s["net_main20"] * (0.9 + 0.2 * self._rng.random()), 2),
                "chg10": round(chg * 1.2 + self._rng.normal(0, 2), 2),
                "ddx10": round(self._rng.normal(0, 0.6), 2),
                "chg20": round(chg * 1.5 + self._rng.normal(0, 3), 2),
                "ddx20": round(self._rng.normal(0, 0.7), 2),
                "chg60": round(self._rng.normal(0, 15), 2),
                "chg_yy": round(self._rng.normal(0, 30), 2),
                # 实时估值随价微变
                "pb": round(s["pb"] * (price / s["base_price"]), 2),
                "pe_static": round(s["pe_static"], 2),
                "pe_ttm": round(s["pe_ttm"] * (s["base_price"] / price), 2),
                "pe_dyn": round(s["pe_dyn"] * (s["base_price"] / price), 2),
            })
        # 计算 4 周期 x 2 口径的主力增仓% (真实公式, 非随机)
        rows = [compute_main_positions(r) for r in rows]
        return rows


# ------------------------------------------------------------------
# 3. 筛选引擎 (快变量过滤 + diff 进出局)
# ------------------------------------------------------------------
STRENGTH_RANK = {"strong": 5, "mid_strong": 4, "mid": 3, "mid_weak": 2, "weak": 1, "none": 0}

# 默认参数: 宽松优先, 保证有结果, 用户再逐步收紧
DEFAULT_PARAMS = {
    "price_max": 1000, "in_out_ratio_max": 5.0, "vol_ratio_min": 0.0, "turn_min": 0.0, "amount_min": 0.0,
    "ddx1_min": -10.0, "ddx5_min": -10.0, "ddx10_min": -10.0, "ddx20_min": -10.0,
    # 主力增仓% 双口径阈值 (自由流通市值口径=主, 成交额口径=辅), n日
    # 默认 0.0: "主力增仓"语义上应为正值 (>0 表示净流入/增仓), 放宽可拖到负数
    "main_pos1_free_min": 0.0, "main_pos1_amt_min": 0.0,
    "main_pos5_free_min": 0.0, "main_pos5_amt_min": 0.0,
    "main_pos10_free_min": 0.0, "main_pos10_amt_min": 0.0,
    "main_pos20_free_min": 0.0, "main_pos20_amt_min": 0.0,
    "circ_mv_min": 100, "pb_max": 100.0,
    "pe_dyn_max": 500.0, "pe_static_max": 500.0, "pe_ttm_max": 500.0,
    "pe_dyn_static_ratio_max": 5.0, "pe_dyn_ttm_ratio_max": 5.0,
    "roe_min": -100.0, "debt_ratio_max": 100.0, "div_yield_min": 0.0, "peg_max": 10.0,
    "max_cycle_strength": "mid_weak",
    "excluded_sw_l2": ["煤炭开采", "石油开采", "工业金属"],
}


def fast_filter(snapshot: List[Dict], params: Dict) -> List[Dict]:
    """盘中快筛: 按 params 里的阈值过滤"""
    out = []
    for r in snapshot:
        # 主板 (此处 mock 均为主板, 实盘用 ts_code 后缀过滤)
        # 股价
        if not (params["price_max"] >= r["price"] >= 0):
            continue
        # 内外比
        if r["in_out_ratio"] >= params["in_out_ratio_max"]:
            continue
        # DDX 当日 / 5 / 10 / 20
        if r["ddx1"] <= params["ddx1_min"]:
            continue
        if r["ddx5"] <= params["ddx5_min"]:
            continue
        if r["ddx10"] <= params["ddx10_min"]:
            continue
        if r["ddx20"] <= params["ddx20_min"]:
            continue
        # ---- 主力增仓% 双口径 (自由流通市值口径 主 / 成交额口径 辅) ----
        if (r.get("main_pos1", 0) or 0) <= params.get("main_pos1_free_min", -99):
            continue
        if (r.get("main_pos5", 0) or 0) <= params.get("main_pos5_free_min", -99):
            continue
        if (r.get("main_pos10", 0) or 0) <= params.get("main_pos10_free_min", -99):
            continue
        if (r.get("main_pos20", 0) or 0) <= params.get("main_pos20_free_min", -99):
            continue
        if r.get("main_pos1_amt") is not None and r["main_pos1_amt"] <= params.get("main_pos1_amt_min", -99):
            continue
        if r.get("main_pos5_amt") is not None and r["main_pos5_amt"] <= params.get("main_pos5_amt_min", -99):
            continue
        if r.get("main_pos10_amt") is not None and r["main_pos10_amt"] <= params.get("main_pos10_amt_min", -99):
            continue
        if r.get("main_pos20_amt") is not None and r["main_pos20_amt"] <= params.get("main_pos20_amt_min", -99):
            continue
        # 量比
        if r["vol_ratio"] <= params["vol_ratio_min"]:
            continue
        # 换手率 (开盘可能 None, 此处模拟已给值)
        if r["turn"] < params["turn_min"]:
            continue
        # 金额
        if r["amount"] < params["amount_min"]:
            continue
        # 流通市值
        if r["circ_mv"] < params["circ_mv_min"]:
            continue
        # 市净率 0 ~ 均值 (均值由快照统计, 此处用 param)
        if not (0 < r["pb"] <= params["pb_max"]):
            continue
        # 动态/静态/TTM PE < 均值
        if not (0 < r["pe_dyn"] <= params["pe_dyn_max"]):
            continue
        if not (0 < r["pe_static"] <= params["pe_static_max"]):
            continue
        if not (0 < r["pe_ttm"] <= params["pe_ttm_max"]):
            continue
        # 动态PE/静态PE < 1, 动态PE/TTM < 1
        if r["pe_dyn"] / max(r["pe_static"], 1e-9) >= params["pe_dyn_static_ratio_max"]:
            continue
        if r["pe_dyn"] / max(r["pe_ttm"], 1e-9) >= params["pe_dyn_ttm_ratio_max"]:
            continue
        # 市现率 (经营现金流/市值) < 25%
        # mock 未给现金流, 用 pe_ttm 近似跳过 (实盘接入)
        # PEG = 动态PE / 利润同比% < 1
        if r["profit_yoy"] > 0 and r["pe_dyn"] / r["profit_yoy"] >= params["peg_max"]:
            continue
        # ROE > 5%
        if r["roe"] <= params["roe_min"]:
            continue
        # 资产负债率 < 66.67%
        if r["debt_ratio"] >= params["debt_ratio_max"]:
            continue
        # 股息率 > 2.5%
        if r["div_yield"] <= params["div_yield_min"]:
            continue
        # ---- 周期股过滤 ----
        strength = STRENGTH_RANK.get(r.get("cycle", "none"), 0)
        if strength > STRENGTH_RANK.get(params["max_cycle_strength"], 99):
            continue
        if r.get("sw_l2") in params.get("excluded_sw_l2", []):
            continue

        out.append(r)
    return out


def diagnose(snapshot: List[Dict], params: Dict) -> Dict[str, int]:
    """诊断: 每个条件分别淘汰了多少只. 结果为空时定位卡点."""
    from collections import defaultdict
    counts = defaultdict(int)
    for r in snapshot:
        checks = [
            ("股价", params["price_max"] >= r["price"] >= 0),
            ("内外比", r["in_out_ratio"] < params["in_out_ratio_max"]),
            ("当日DDX", r["ddx1"] > params["ddx1_min"]),
            ("5日DDX", r["ddx5"] > params["ddx5_min"]),
            ("10日DDX", r["ddx10"] > params["ddx10_min"]),
            ("20日DDX", r["ddx20"] > params["ddx20_min"]),
            # 增仓% 自由流通市值口径
            ("当日增仓%自由", (r.get("main_pos1", 0) or 0) > params.get("main_pos1_free_min", -99)),
            ("5日增仓%自由", (r.get("main_pos5", 0) or 0) > params.get("main_pos5_free_min", -99)),
            ("10日增仓%自由", (r.get("main_pos10", 0) or 0) > params.get("main_pos10_free_min", -99)),
            ("20日增仓%自由", (r.get("main_pos20", 0) or 0) > params.get("main_pos20_free_min", -99)),
            # 增仓% 成交额口径 (None=开盘未就绪, 不淘汰)
            ("当日增仓%金额", r.get("main_pos1_amt") is None or r["main_pos1_amt"] > params.get("main_pos1_amt_min", -99)),
            ("5日增仓%金额", r.get("main_pos5_amt") is None or r["main_pos5_amt"] > params.get("main_pos5_amt_min", -99)),
            ("10日增仓%金额", r.get("main_pos10_amt") is None or r["main_pos10_amt"] > params.get("main_pos10_amt_min", -99)),
            ("20日增仓%金额", r.get("main_pos20_amt") is None or r["main_pos20_amt"] > params.get("main_pos20_amt_min", -99)),
            ("量比", r["vol_ratio"] > params["vol_ratio_min"]),
            ("换手率", r["turn"] >= params["turn_min"]),
            ("成交金额", r["amount"] >= params["amount_min"]),
            ("流通市值", r["circ_mv"] >= params["circ_mv_min"]),
            ("市净率", 0 < r["pb"] <= params["pb_max"]),
            ("动态PE", 0 < r["pe_dyn"] <= params["pe_dyn_max"]),
            ("静态PE", 0 < r["pe_static"] <= params["pe_static_max"]),
            ("TTM PE", 0 < r["pe_ttm"] <= params["pe_ttm_max"]),
            ("PE动/静", r["pe_dyn"] / max(r["pe_static"], 1e-9) < params["pe_dyn_static_ratio_max"]),
            ("PE动/TTM", r["pe_dyn"] / max(r["pe_ttm"], 1e-9) < params["pe_dyn_ttm_ratio_max"]),
            ("PEG", r["profit_yoy"] <= 0 or r["pe_dyn"] / r["profit_yoy"] < params["peg_max"]),
            ("ROE", r["roe"] > params["roe_min"]),
            ("资产负债率", r["debt_ratio"] < params["debt_ratio_max"]),
            ("股息率", r["div_yield"] > params["div_yield_min"]),
            ("周期强度", STRENGTH_RANK.get(r.get("cycle", "none"), 0) <= STRENGTH_RANK.get(params["max_cycle_strength"], 99)),
            ("二级行业排除", r.get("sw_l2") not in params.get("excluded_sw_l2", [])),
        ]
        for key, ok in checks:
            counts[key] = counts.get(key, 0)
            if not ok:
                counts[key] += 1
    return counts


# ------------------------------------------------------------------
# 4. 格式化 + 样式
# ------------------------------------------------------------------
def fmt_value(col_key: str, val) -> str:
    """按列配置把值格式化为字符串 (不带单位符号, 节省宽度)"""
    cfg = COL_MAP[col_key]
    if val is None:
        return ""
    if isinstance(val, (int, float, np.floating)):
        if cfg["decimals"] is not None:
            return f"{val:.{cfg['decimals']}f}"
        return str(int(val))
    return str(val)


def colorize(row: Dict, prev_row: Optional[Dict]) -> Dict[str, str]:
    """按涨跌/资金方向着色; 与上一轮比较做闪烁高亮"""
    style = {}
    chg = row.get("chg_pct", 0)
    style["chg_pct"] = "color:#ff4d4f" if chg > 0 else ("color:#0ecb81" if chg < 0 else "")
    style["price"] = style["chg_pct"]
    for k in ["chg5", "chg10", "chg20", "chg60", "chg_yy"]:
        v = row.get(k, 0)
        style[k] = "color:#ff4d4f" if v > 0 else ("color:#0ecb81" if v < 0 else "")
    for k in ["ddx1", "ddx5", "ddx10", "ddx20", "main_pos1", "main_pos5", "main_pos10", "main_pos20"]:
        v = row.get(k, 0)
        style[k] = "color:#ff4d4f" if v > 0 else ("color:#0ecb81" if v < 0 else "")
    for k in ["net_super", "net_big", "net_mid", "net_small", "main_flow"]:
        v = row.get(k, 0)
        style[k] = "color:#ff4d4f" if v > 0 else ("color:#0ecb81" if v < 0 else "")
    # 新进入 / 刚出局高亮
    if prev_row is None:
        style["__row__"] = "background-color: rgba(255, 77, 79, 0.15)"
    return style


def estimate_col_width(chars: int) -> int:
    """字符数 -> 像素 (9pt/15px 字号, 中文按1.8倍宽)"""
    # 采用固定字符宽度: 每字符约 8.6px (15px 字号下 avg)
    return int(chars * 8.6 + 12)


# ------------------------------------------------------------------
# 5. Streamlit 页面
# ------------------------------------------------------------------
st.set_page_config(
    page_title="沪深京实时行情筛选器",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 全局 CSS: 紧凑表格 + 9px 字号
st.markdown("""
<style>
html, body, .stApp { font-size: 15px; }
table { border-collapse: collapse; }
thead th {
    font-size: 15px !important;
    font-weight: 600;
    text-align: left !important;
    white-space: nowrap;
    padding: 2px 4px !important;
    border-bottom: 1px solid #333;
    color: #bbb;
}
tbody td {
    font-size: 15px !important;
    padding: 1px 4px !important;
    white-space: nowrap;
}
tbody tr:hover { background: rgba(255,255,255,0.06); }
div[data-testid="stDataFrame"] { font-size: 15px; }
</style>
""", unsafe_allow_html=True)


def main():
    # ---- 侧边栏: 筛选条件控件 ----
    with st.sidebar:
        st.title("筛选条件")

        st.subheader("行情")
        price_max = st.number_input("股价上限 (元)", 1, 1000, 1000)
        in_out_ratio_max = st.number_input("内外比 <", 0.0, 5.0, 5.0, 0.1)
        vol_ratio_min = st.number_input("量比 >", 0.0, 10.0, 0.0, 0.1)
        turn_min = st.number_input("换手率% >", 0.0, 100.0, 0.0, 0.1)
        amount_min = st.number_input("成交金额(亿) >", 0.0, 1000.0, 0.0, 0.5)

        st.subheader("DDX / 主力增仓%")
        ddx1_min = st.number_input("当日DDX >", -10.0, 10.0, -10.0, 0.1)
        ddx5_min = st.number_input("5日DDX >", -10.0, 10.0, -10.0, 0.1)
        ddx10_min = st.number_input("10日DDX >", -10.0, 10.0, -10.0, 0.1)
        ddx20_min = st.number_input("20日DDX >", -10.0, 10.0, -10.0, 0.1)

        # ---- n日主力增仓%: 双口径阈值 (自由流通市值口径 主 / 成交额口径 辅) ----
        # 口径A = 主力净额 / 自由流通市值 * 100  (跨市值可比, 主指标, 用于筛选排序)
        # 口径B = 主力净额 / 当日总成交额 * 100  (看主力当天主导力, 辅指标)
        # 成交额口径开盘初期(成交额=0)自动为 None, 不参与淘汰 (= 逐步入围)
        st.markdown("**主力增仓% — 自由流通市值口径** *(主, 跨市值可比)*")
        main_pos1_free_min = st.slider("当日增仓%自由 >", -10.0, 10.0, 0.0, 0.1)
        main_pos5_free_min = st.slider("5日增仓%自由 >", -10.0, 10.0, 0.0, 0.1)
        main_pos10_free_min = st.slider("10日增仓%自由 >", -10.0, 10.0, 0.0, 0.1)
        main_pos20_free_min = st.slider("20日增仓%自由 >", -10.0, 10.0, 0.0, 0.1)
        st.markdown("**主力增仓% — 成交额口径** *(辅, 看主力主导力; 开盘未就绪不淘汰)*")
        main_pos1_amt_min = st.slider("当日增仓%金额 >", -10.0, 10.0, 0.0, 0.1)
        main_pos5_amt_min = st.slider("5日增仓%金额 >", -10.0, 10.0, 0.0, 0.1)
        main_pos10_amt_min = st.slider("10日增仓%金额 >", -10.0, 10.0, 0.0, 0.1)
        main_pos20_amt_min = st.slider("20日增仓%金额 >", -10.0, 10.0, 0.0, 0.1)

        st.subheader("市值 / 估值")
        circ_mv_min = st.number_input("流通市值(亿) >", 0, 100000, 100)
        pb_max = st.number_input("市净率 <", 0.0, 100.0, 100.0, 0.5)
        pe_dyn_max = st.number_input("动态PE < (均值)", 0.0, 500.0, 500.0, 1.0)
        pe_static_max = st.number_input("静态PE < (均值)", 0.0, 500.0, 500.0, 1.0)
        pe_ttm_max = st.number_input("TTM PE < (均值)", 0.0, 500.0, 500.0, 1.0)
        pe_dyn_static_ratio = st.number_input("动态PE/静态PE <", 0.0, 5.0, 5.0, 0.1)
        pe_dyn_ttm_ratio = st.number_input("动态PE/TTM <", 0.0, 5.0, 5.0, 0.1)

        st.subheader("财务")
        roe_min = st.number_input("ROE% >", -100.0, 100.0, -100.0, 0.5)
        debt_ratio_max = st.number_input("资产负债率% <", 0.0, 100.0, 100.0, 1.0)
        div_yield_min = st.number_input("股息率% >", 0.0, 50.0, 0.0, 0.1)
        peg_max = st.number_input("PEG <", 0.0, 10.0, 10.0, 0.1)

        st.subheader("周期股过滤")
        max_cycle = st.select_slider(
            "最大允许周期强度",
            options=["none", "weak", "mid_weak", "mid", "mid_strong", "strong"],
            value="mid_weak",
        )
        # 申万二级精细排除 (多选)
        all_sw_l2 = sorted({s["sw_l2"] for s in make_mock_pool()})
        excluded_l2 = st.multiselect(
            "精细排除 (申万二级行业)",
            options=all_sw_l2,
            default=["煤炭开采", "石油开采", "工业金属"],
        )

        refresh_rate = st.selectbox("刷新间隔", [1, 3, 5, 10], index=1)

    # 组装参数
    params = {
        "price_max": price_max, "in_out_ratio_max": in_out_ratio_max,
        "vol_ratio_min": vol_ratio_min, "turn_min": turn_min, "amount_min": amount_min,
        "ddx1_min": ddx1_min, "ddx5_min": ddx5_min, "ddx10_min": ddx10_min, "ddx20_min": ddx20_min,
        # 主力增仓% 双口径 (自由流通市值口径 主 / 成交额口径 辅)
        "main_pos1_free_min": main_pos1_free_min, "main_pos1_amt_min": main_pos1_amt_min,
        "main_pos5_free_min": main_pos5_free_min, "main_pos5_amt_min": main_pos5_amt_min,
        "main_pos10_free_min": main_pos10_free_min, "main_pos10_amt_min": main_pos10_amt_min,
        "main_pos20_free_min": main_pos20_free_min, "main_pos20_amt_min": main_pos20_amt_min,
        "circ_mv_min": circ_mv_min, "pb_max": pb_max,
        "pe_dyn_max": pe_dyn_max, "pe_static_max": pe_static_max, "pe_ttm_max": pe_ttm_max,
        "pe_dyn_static_ratio_max": pe_dyn_static_ratio, "pe_dyn_ttm_ratio_max": pe_dyn_ttm_ratio,
        "roe_min": roe_min, "debt_ratio_max": debt_ratio_max, "div_yield_min": div_yield_min, "peg_max": peg_max,
        "max_cycle_strength": max_cycle, "excluded_sw_l2": excluded_l2,
    }

    # ---- 会话状态: 持久化 ----
    if "sim" not in st.session_state:
        st.session_state.sim = MarketSimulator(make_mock_pool())
    if "prev" not in st.session_state:
        st.session_state.prev = {}  # code -> row
    if "history" not in st.session_state:
        st.session_state.history = []  # 进出局事件流
    if "order" not in st.session_state:
        st.session_state.order = DEFAULT_ORDER
    if "col_widths" not in st.session_state:
        st.session_state.col_widths = {c["key"]: estimate_col_width(c["width_chars"]) for c in COLUMNS}

    # ---- 顶部状态栏 ----
    header = st.container()
    with header:
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 2])
        c1.metric("选中条件", f"{len(DEFAULT_ORDER)} 字段")
        pool_size = len(make_mock_pool())
        c2.metric("季度慢池", pool_size)
        # 本轮快照
        snapshot = st.session_state.sim.snapshot()
        selected = fast_filter(snapshot, params)
        prev_map = st.session_state.prev
        curr_codes = {r["code"] for r in selected}
        prev_codes = set(prev_map.keys())
        entered = curr_codes - prev_codes
        exited = prev_codes - curr_codes
        c3.metric("当前入选", len(selected), delta=f"+{len(entered)}")
        c4.metric("本轮回局", len(exited), delta=f"-{len(exited)}" if exited else None)
        c5.write(f"**最后更新**: {datetime.now().strftime('%H:%M:%S')}  ·  "
                 f"下一轮 {refresh_rate}s  ·  "
                 f"涨停色=涨/红  ·  数据: MOCK 模拟")

    # ---- 进出局事件流 ----
    for code in entered:
        r = next(x for x in selected if x["code"] == code)
        st.session_state.history.insert(0, (datetime.now().strftime("%H:%M:%S"), "✅ 进入", f"{code} {r['name']}"))
    for code in exited:
        st.session_state.history.insert(0, (datetime.now().strftime("%H:%M:%S"), "❌ 出局", f"{code} {prev_map.get(code, {}).get('name', '')}"))
    st.session_state.history = st.session_state.history[:50]

    # 更新 prev
    st.session_state.prev = {r["code"]: r for r in selected}

    # ---- 列顺序调整 (拖动模拟: 用 selectbox 多选排序) ----
    with st.expander("列设置: 拖拽排序 / 显隐", expanded=False):
        st.write("勾选并调整字段顺序 (Streamlit 原生拖拽有限, 用右侧 ↑↓ 模拟):")
        order = st.multiselect(
            "显示的字段 (按列表顺序)",
            options=DEFAULT_ORDER,
            default=st.session_state.order,
        )
        st.session_state.order = order
        # 列宽手动微调
        for key in order[:8]:
            cfg = COL_MAP[key]
            st.session_state.col_widths[key] = st.slider(
                f"{cfg['label']} 宽度(px)", 30, 300,
                st.session_state.col_widths[key], key=f"w_{key}"
            )

    # ---- 主表格 ----
    if selected:
        df = pd.DataFrame(selected)
        # 只保留用户选定列, 按 order 排序
        cols = [c for c in st.session_state.order if c in df.columns]
        df = df[cols]

        # 格式化 + 着色
        styled = df.copy()
        # 应用颜色到各列
        for _, row in styled.iterrows():
            prev_r = st.session_state.prev.get(row["code"])
            # 行级高亮由 Styler 处理
        styler = styled.style
        # 数值着色函数
        num_color_cols = ["chg_pct", "chg5", "chg10", "chg20", "chg60", "chg_yy",
                          "ddx1", "ddx5", "ddx10", "ddx20",
                          "main_pos1", "main_pos1_amt", "main_pos5", "main_pos5_amt",
                          "main_pos10", "main_pos10_amt", "main_pos20", "main_pos20_amt",
                          "net_super", "net_big", "net_mid", "net_small", "main_flow", "price"]
        for col in num_color_cols:
            if col in styled.columns:
                styler = styler.map(lambda v: "color:#ff4d4f" if (isinstance(v, (int, float)) and v > 0)
                                    else ("color:#0ecb81" if (isinstance(v, (int, float)) and v < 0) else ""),
                                    subset=[col])

        # 新进入行高亮 (通过 code 匹配)
        def row_highlight(row):
            if row.get("code") in entered:
                return ["background-color: rgba(255,77,79,0.15)"] * len(row)
            return [""] * len(row)

        if "code" in styled.columns:
            styler = styler.apply(row_highlight, axis=1)

        # 格式化所有列为 2 位小数
        fmt_dict = {c["key"]: f"{{:.{c['decimals']}f}}" for c in COLUMNS if c["decimals"] is not None and c["key"] in cols}
        if fmt_dict:
            styler = styler.format(fmt_dict, na_rep="")

        # 列宽 (通过 CSS 变量 + 表头宽度)
        width_css = "<style>"
        for i, key in enumerate(cols):
            w = st.session_state.col_widths.get(key, 80)
            width_css += f"table th:nth-child({i+1}), table td:nth-child({i+1}) {{ min-width:{w}px; max-width:{w}px; width:{w}px; }}\n"
        width_css += "</style>"
        st.markdown(width_css, unsafe_allow_html=True)

        st.dataframe(
            styler,
            use_container_width=True,
            height=600,
            hide_index=True,
        )
    else:
        st.warning("当前无满足条件的标的, 请放宽筛选条件.")
        # 空结果诊断: 提示用户哪个条件太严
        diag = diagnose(snapshot, params)
        sorted_diag = sorted(diag.items(), key=lambda x: -x[1])
        top = [(k, v) for k, v in sorted_diag if v > 0][:5]
        if top:
            st.info("💡 **建议放宽以下过严条件:**")
            for k, v in top:
                st.write(f"  · {k}: 淘汰了 {v}/{len(snapshot)} 只")

    # ---- 右侧: 进出局日志 + 字段说明 ----
    col_log, col_help = st.columns([1, 1])
    with col_log:
        st.subheader("📋 进出局日志")
        if st.session_state.history:
            log_df = pd.DataFrame(st.session_state.history, columns=["时间", "事件", "标的"])
            st.dataframe(log_df, hide_index=True, height=300)
        else:
            st.caption("尚无进出局事件")
    with col_help:
        st.subheader("ℹ️ 说明")
        st.caption("""
        - **架构**: 季度慢池(财报) + 盘中快筛(行情) + diff 自动进出
        - **周期股**: 申万行业分级(strong/mid_strong/mid/mid_weak/weak/none) + 二级精细排除
        - **实时性**: 当前为 MOCK 模拟; 接 akshare `stock_zh_a_spot_em` + tushare `daily_basic` 即可实盘
        - **字段**: 小数统一2位; 金额按亿; 单位符号(亿/%)省略以省宽度
        - **字号**: 15px, 一屏多字段
        """)
        with st.expander("周期强度对照"):
            st.write({
                "strong": "煤炭/有色/石化/化工/钢铁",
                "mid_strong": "建材/建筑/地产",
                "mid": "机械/电力设备/公用事业/交运",
                "mid_weak": "汽车/农林牧渔/贵金属",
                "weak": "银行/食品饮料",
            })

    # ---- 自动刷新 (streamlit 原生轮询) ----
    # 说明: Streamlit 不支持后台长轮询, 用 st_autorefresh 或定时 rerun 替代
    # 本地运行时可取消下行注释以启用自动刷新:
    # from streamlit_autorefresh import st_autorefresh
    # st_autorefresh(interval=refresh_rate * 1000, key="refresh")
    st.caption(f"💡 启用自动刷新: 安装 `streamlit-autorefresh`, 当前手动刷新请按 F5 / Cmd+R")


if __name__ == "__main__":
    main()
