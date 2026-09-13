# -*- coding: utf-8 -*-
"""
沪深京实时行情筛选器 (Streamlit 前端)

架构: 季度慢池(财报) + 盘中快筛(行情) + diff 自动进出
周期股过滤: 申万行业分级 + 周期性评分

运行:
    pip install streamlit pandas akshare python-dotenv
    streamlit run app.py

数据源 (环境变量切换, 无需改代码):
    DATASOURCE=realtime  (默认, 腾讯+AkShare, 无需 token)
    DATASOURCE=mock       (强制模拟)
    DATASOURCE=tushare    (TuShare, 需 TUSHARE_TOKEN, 有限流)
    USE_MANUAL_POOL=true  (默认, 用 manual_pool.csv; false=全市场主板)
"""

import os
import sys
import time
import traceback
from datetime import datetime
from typing import List, Dict, Optional

import numpy as np
import pandas as pd
import streamlit as st

# 兼容导入：任一数据源缺失都能降级 MOCK, 保证界面可运行
try:
    from data_source import DataSource as TuShareDataSource
    _HAS_TUSHARE_DS = True
except Exception:
    _HAS_TUSHARE_DS = False

try:
    from realtime_source import RealtimeDataSource
    _HAS_REALTIME_DS = True
except Exception:
    _HALTIME_DS = False  # noqa
    _HAS_REALTIME_DS = False


# ==================================================================
# 调试/状态开关 (侧边栏可关闭; 生产环境设为 False)
# ==================================================================
DEBUG = os.getenv("DEBUG", "true").lower() in ("1", "true", "yes")


def _safe(val, default="", fmt=str):
    """格式化安全网: 避免 None / nan 触发 Styler 报错"""
    if val is None:
        return default
    if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
        return default
    try:
        return fmt(val)
    except Exception:
        return default


# ------------------------------------------------------------------
# 1. 字段元配置
# ------------------------------------------------------------------
COLUMNS: List[Dict] = [
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
    {"key": "main_pos1",     "label": "当日增仓%自由流通市值", "width_chars": 11, "decimals": 2, "align": "right", "group": "DDX"},
    {"key": "main_pos1_amt", "label": "当日增仓%总金额", "width_chars": 11, "decimals": 2, "align": "right", "group": "DDX"},
    {"key": "in_out_ratio","label": "内外比",  "width_chars": 6,  "decimals": 2,    "align": "right", "group": "盘口"},
    {"key": "vol_ratio",   "label": "量比",   "width_chars": 5,  "decimals": 2,    "align": "right", "group": "盘口"},
    {"key": "turn",        "label": "换手率%", "width_chars": 7,  "decimals": 2,    "align": "right", "group": "盘口"},
    {"key": "amount",      "label": "总金额(亿)", "width_chars": 8, "decimals": 2,  "align": "right", "group": "盘口"},
    {"key": "chg5",        "label": "5日涨幅%", "width_chars": 8, "decimals": 2,   "align": "right", "group": "阶段"},
    {"key": "ddx5",        "label": "5日DDX",  "width_chars": 7,  "decimals": 2,   "align": "right", "group": "阶段"},
    {"key": "main_pos5",     "label": "5日增仓%自由流通市值", "width_chars": 11, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "main_pos5_amt", "label": "5日增仓%总金额", "width_chars": 11, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg10",       "label": "10日涨幅%", "width_chars": 9, "decimals": 2,  "align": "right", "group": "阶段"},
    {"key": "ddx10",       "label": "10日DDX", "width_chars": 8,  "decimals": 2,   "align": "right", "group": "阶段"},
    {"key": "main_pos10",     "label": "10日增仓%自由流通市值", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "main_pos10_amt", "label": "10日增仓%总金额", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg20",       "label": "20日涨幅%", "width_chars": 9, "decimals": 2,  "align": "right", "group": "阶段"},
    {"key": "ddx20",       "label": "20日DDX", "width_chars": 8,  "decimals": 2,   "align": "right", "group": "阶段"},
    {"key": "main_pos20",     "label": "20日增仓%自由流通市值", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "main_pos20_amt", "label": "20日增仓%总金额", "width_chars": 12, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "chg60",       "label": "60日涨幅%", "width_chars": 9, "decimals": 2,  "align": "right", "group": "阶段"},
    {"key": "chg_yy",      "label": "近一年涨幅%", "width_chars": 10, "decimals": 2, "align": "right", "group": "阶段"},
    {"key": "total_mv",    "label": "总市值(亿)", "width_chars": 8,  "decimals": 2,   "align": "right", "group": "估值"},
    {"key": "circ_mv",     "label": "流通市值(亿)", "width_chars": 9, "decimals": 2,  "align": "right", "group": "估值"},
    {"key": "pb",          "label": "市净率",  "width_chars": 6,  "decimals": 2,    "align": "right", "group": "估值"},
    {"key": "pe_static",   "label": "PE(静)",    "width_chars": 7,  "decimals": 2,    "align": "right", "group": "估值"},
    {"key": "pe_ttm",      "label": "PE(TTM)", "width_chars": 8,  "decimals": 2,    "align": "right", "group": "估值"},
    {"key": "pe_dyn",      "label": "PE(动)",    "width_chars": 6,  "decimals": 2,    "align": "right", "group": "估值"},
    {"key": "profit_yoy",  "label": "利润同比%", "width_chars": 10, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "rev_yoy",     "label": "营收同比%", "width_chars": 11, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "roe",         "label": "净资产收益率%", "width_chars": 11, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "gross_margin","label": "毛利率%",  "width_chars": 8,  "decimals": 2,   "align": "right", "group": "财务"},
    {"key": "debt_ratio",  "label": "资产负债率%", "width_chars": 10, "decimals": 2, "align": "right", "group": "财务"},
    {"key": "div_yield",   "label": "股息率%",  "width_chars": 7,  "decimals": 2,   "align": "right", "group": "财务"},
]

COL_MAP = {c["key"]: c for c in COLUMNS}
DEFAULT_ORDER = [c["key"] for c in COLUMNS]
# 所有声明字段的默认缺失值 (保证 df[cols] 永远不缺列, 根除 Styler 崩溃)
DEFAULT_ROW = {c["key"]: (0.0 if c["decimals"] is not None else "") for c in COLUMNS}


# ------------------------------------------------------------------
# 主力增仓% 计算
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
# MOCK 数据源
# ------------------------------------------------------------------
def make_mock_pool():
    return [
    {"code": "000001", "name": "平安银行", "sw_l1": "银行", "sw_l2": "股份制银行", "cycle": "weak",
      "profit_yoy": 8.5, "rev_yoy": 5.2, "roe": 12.3, "gross_margin": 55.0, "debt_ratio": 92.0, "div_yield": 3.2,
      "total_mv": 2200, "circ_mv": 2200, "free_circ_mv": 1800, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "price": 12.5, 
      "base_price": 12.5, "base_amount": 5.0,
      "net_super": 0.5, "net_big": 0.3, "net_mid": -0.3, "net_small": -0.5,
      "net_main5": 3.0, "net_main10": 6.0, "net_main20": 9.0},
    {"code": "600036", "name": "招商银行", "sw_l1": "银行", "sw_l2": "股份制银行", "cycle": "weak",
      "price": 38.2,
      "profit_yoy": 6.3, "rev_yoy": 4.1, "roe": 15.0, "gross_margin": 60.0, "debt_ratio": 91.0, "div_yield": 4.5,
      "total_mv": 9500, "circ_mv": 9500, "free_circ_mv": 7600, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "price": 38.2, 
      "base_price": 38.2, "base_amount": 12.0,
      "net_super": 1.0, "net_big": 0.8, "net_mid": -0.7, "net_small": -1.1,
      "net_main5": 8.0, "net_main10": 15.0, "net_main20": 22.0},
    {"code": "601318", "name": "中国平安", "sw_l1": "非银金融", "sw_l2": "保险", "cycle": "mid_weak",
      "profit_yoy": 12.0, "rev_yoy": 7.5, "roe": 13.0, "gross_margin": 50.0, "debt_ratio": 88.0, "div_yield": 3.8,
      "total_mv": 9000, "circ_mv": 9000, "free_circ_mv": 7200, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "price": 52.0, 
      "base_price": 52.0, "base_amount": 18.0,
      "net_super": 1.2, "net_big": 0.9, "net_mid": -0.8, "net_small": -1.3,
      "net_main5": 9.0, "net_main10": 18.0, "net_main20": 26.0},
    {"code": "600519", "name": "贵州茅台", "sw_l1": "食品饮料", "sw_l2": "白酒", "cycle": "weak",
      "profit_yoy": 15.0, "rev_yoy": 16.0, "roe": 30.0, "gross_margin": 92.0, "debt_ratio": 20.0, "div_yield": 1.5,
      "total_mv": 21000, "circ_mv": 21000, "free_circ_mv": 16000, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "price": 1680.0, 
      "base_price": 1680.0, "base_amount": 30.0,
      "net_super": 2.5, "net_big": 1.5, "net_mid": -1.6, "net_small": -2.4,
      "net_main5": 15.0, "net_main10": 28.0, "net_main20": 45.0},
    {"code": "000333", "name": "美的集团", "sw_l1": "家用电器", "sw_l2": "空调", "cycle": "mid_weak",
      "profit_yoy": 10.0, "rev_yoy": 8.0, "roe": 22.0, "gross_margin": 28.0, "debt_ratio": 62.0, "div_yield": 3.5,
      "total_mv": 4800, "circ_mv": 4700, "free_circ_mv": 3800, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "price": 68.0, 
      "base_price": 68.0, "base_amount": 8.0,
      "net_super": 0.6, "net_big": 0.4, "net_mid": -0.4, "net_small": -0.6,
      "net_main5": 4.0, "net_main10": 8.0, "net_main20": 12.0},
    {"code": "600900", "name": "长江电力", "sw_l1": "公用事业", "sw_l2": "水电", "cycle": "mid",
      "profit_yoy": 5.0, "rev_yoy": 4.0, "roe": 15.5, "gross_margin": 65.0, "debt_ratio": 55.0, "div_yield": 3.0,
      "total_mv": 5600, "circ_mv": 5500, "free_circ_mv": 4400, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "price": 24.5, 
      "base_price": 24.5, "base_amount": 6.0,
      "net_super": 0.4, "net_big": 0.3, "net_mid": -0.3, "net_small": -0.4,
      "net_main5": 2.5, "net_main10": 5.0, "net_main20": 8.0},
    {"code": "601088", "name": "中国神华", "sw_l1": "煤炭", "sw_l2": "煤炭开采", "cycle": "strong",
      "profit_yoy": -8.0, "rev_yoy": -5.0, "roe": 14.0, "gross_margin": 40.0, "debt_ratio": 45.0, "div_yield": 6.0,
      "total_mv": 6200, "circ_mv": 5000, "free_circ_mv": 3800, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "price": 32.0, 
      "base_price": 32.0, "base_amount": 10.0,
      "net_super": 0.7, "net_big": 0.5, "net_mid": -0.5, "net_small": -0.7,
      "net_main5": 5.0, "net_main10": 9.0, "net_main20": 14.0},
    {"code": "600028", "name": "中国石化", "sw_l1": "石油石化", "sw_l2": "石油开采", "cycle": "strong",
      "profit_yoy": -15.0, "rev_yoy": -10.0, "roe": 8.0, "gross_margin": 20.0, "debt_ratio": 50.0, "div_yield": 4.0,
      "total_mv": 7000, "circ_mv": 6000, "free_circ_mv": 4500, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "price": 6.2, 
      "base_price": 6.2, "base_amount": 7.0,
      "net_super": 0.5, "net_big": 0.4, "net_mid": -0.4, "net_small": -0.5,
      "net_main5": 3.5, "net_main10": 6.5, "net_main20": 10.0},
    {"code": "601899", "name": "紫金矿业", "sw_l1": "有色金属", "sw_l2": "工业金属", "cycle": "strong",
      "profit_yoy": 25.0, "rev_yoy": 20.0, "roe": 18.0, "gross_margin": 35.0, "debt_ratio": 58.0, "div_yield": 2.0,
      "total_mv": 4000, "circ_mv": 3500, "free_circ_mv": 2800, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "price": 15.3, 
      "base_price": 15.3, "base_amount": 15.0,
      "net_super": 1.5, "net_big": 1.0, "net_mid": -1.0, "net_small": -1.5,
      "net_main5": 10.0, "net_main10": 19.0, "net_main20": 30.0},
    {"code": "600547", "name": "山东黄金", "sw_l1": "有色金属", "sw_l2": "贵金属", "cycle": "mid_weak",
      "profit_yoy": 30.0, "rev_yoy": 22.0, "roe": 10.0, "gross_margin": 25.0, "debt_ratio": 60.0, "div_yield": 1.0,
      "total_mv": 1200, "circ_mv": 1100, "free_circ_mv": 900, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "price": 28.0, 
      "base_price": 28.0, "base_amount": 9.0,
      "net_super": 0.6, "net_big": 0.4, "net_mid": -0.4, "net_small": -0.6,
      "net_main5": 4.0, "net_main10": 7.0, "net_main20": 11.0},
    {"code": "000002", "name": "万科A", "sw_l1": "房地产", "sw_l2": "住宅开发", "cycle": "mid_strong",
      "profit_yoy": -40.0, "rev_yoy": -25.0, "roe": 5.0, "gross_margin": 18.0, "debt_ratio": 75.0, "div_yield": 2.8,
      "total_mv": 1500, "circ_mv": 1400, "free_circ_mv": 1100, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "price": 9.5, 
      "base_price": 9.5, "base_amount": 4.0,
      "net_super": -0.3, "net_big": -0.2, "net_mid": 0.2, "net_small": 0.3,
      "net_main5": -2.0, "net_main10": -4.0, "net_main20": -6.0},
    {"code": "300750", "name": "宁德时代", "sw_l1": "电力设备", "sw_l2": "电池", "cycle": "mid",
      "profit_yoy": 35.0, "rev_yoy": 40.0, "roe": 22.0, "gross_margin": 30.0, "debt_ratio": 60.0, "div_yield": 1.2,
      "total_mv": 11000, "circ_mv": 9500, "free_circ_mv": 6000, "pb": 1.0, "pe_static": 10.0, "pe_ttm": 9.5, "pe_dyn": 9.0,
      "price": 220.0, 
      "base_price": 220.0, "base_amount": 45.0,
      "net_super": 3.0, "net_big": 2.0, "net_mid": -2.0, "net_small": -3.0,
      "net_main5": 20.0, "net_main10": 40.0, "net_main20": 60.0},
    ]


class MarketSimulator:
    """MOCK 实时行情模拟 (仅离线/降级时使用)"""

    def __init__(self, pool: List[Dict], tick_seconds: int = 3):
        self.pool = pool
        self.tick = 0
        self.tick_seconds = tick_seconds
        self._rng = np.random.default_rng(42)

    def snapshot(self) -> List[Dict]:
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
                "in_out_ratio": round(max(0.3, 1.0 + self._rng.normal(0, 0.2)), 2),
                "vol_ratio": round(max(0.2, 1.0 + self._rng.normal(0, 0.4)), 2),
                "turn": round(turn, 2), "amount": round(amount, 2),
                "chg5": round(chg * 0.8 + self._rng.normal(0, 1), 2),
                "ddx5": round(self._rng.normal(0, 0.5), 2),
                "net_main5": round(s["net_main5"] * (0.9 + 0.2 * self._rng.random()), 2),
                "net_main10": round(s["net_main10"] * (0.9 + 0.2 * self._rng.random()), 2),
                "net_main20": round(s["net_main20"] * (0.9 + 0.2 * self._rng.random()), 2),
                "chg10": round(chg * 1.2 + self._rng.normal(0, 2), 2),
                "ddx10": round(self._rng.normal(0, 0.6), 2),
                "chg20": round(chg * 1.5 + self._rng.normal(0, 3), 2),
                "ddx20": round(self._rng.normal(0, 0.7), 2),
                "chg60": round(self._rng.normal(0, 15), 2),
                "chg_yy": round(self._rng.normal(0, 30), 2),
                "pb": round(s["pb"] * (price / s["base_price"]), 2),
                "pe_static": round(s["pe_static"], 2),
                "pe_ttm": round(s["pe_ttm"] * (s["base_price"] / price), 2),
                "pe_dyn": round(s["pe_dyn"] * (s["base_price"] / price), 2),
            })
        rows = [compute_main_positions(r) for r in rows]
        return rows


# ------------------------------------------------------------------
# 数据源工厂 (统一接口, 任一缺失自动降级)
# ------------------------------------------------------------------
def build_data_source():
    ds_mode = os.getenv("DATASOURCE", "realtime").lower()
    use_manual = os.getenv("USE_MANUAL_POOL", "true").lower() in ("1", "true", "yes")

    if ds_mode == "tushare" and _HAS_TUSHARE_DS:
        return TuShareDataSource(pool=make_mock_pool(), use_real=True)
    if ds_mode == "mock":
        return TuShareDataSource(pool=make_mock_pool(), use_real=False)
    if ds_mode == "realtime" and _HAS_REALTIME_DS:
        return RealtimeDataSource(
            pool=make_mock_pool(),
            manual_pool_path="manual_pool.csv",
            use_manual_pool=use_manual,
            enrich_finance=False,
        )
    # 兜底: 用内置 MOCK (保证界面永不崩溃)
    sim = MarketSimulator(make_mock_pool())

    class _MockDS:
        source = "MOCK"
        error = "无可用数据源 (realtime_source/data_source 未就绪)"

        def get_pool(self):
            return make_mock_pool()

        def snapshot(self, pool):
            return sim.snapshot()

    return _MockDS()


# 让真实快照的 dict 补齐 DEFAULT_ROW, 防止缺列导致 Styler 崩溃
def _normalize(row: Dict) -> Dict:
    merged = dict(DEFAULT_ROW)
    merged.update({k: v for k, v in (row or {}).items() if v is not None})
    return merged


# ------------------------------------------------------------------
# 筛选引擎
# ------------------------------------------------------------------
STRENGTH_RANK = {"strong": 5, "mid_strong": 4, "mid": 3, "mid_weak": 2, "weak": 1, "none": 0}

DEFAULT_PARAMS = {
    "price_max": 50, "in_out_ratio_max": 3.5, "vol_ratio_min": 0.6, "turn_min": 0.33, "amount_min": 0.0,
    "ddx1_min": -1.0, "ddx5_min": -1.0, "ddx10_min": -1.0, "ddx20_min": -1.0,
    "main_pos1_free_min": -1.0, "main_pos1_amt_min": -10.0,
    "main_pos5_free_min": -1.0, "main_pos5_amt_min": -10.0,
    "main_pos10_free_min": -1.0, "main_pos10_amt_min": -10.0,
    "main_pos20_free_min": -1.0, "main_pos20_amt_min": -10.0,
    "circ_mv_min": 100, "pb_max": 100.0, "pe_static_max": 500.0, "pe_ttm_max": 500.0, "pe_dyn_max": 500.0,
    "pe_dyn_static_ratio_max": 1.0, "pe_dyn_ttm_ratio_max": 1.0, "peg_max": 1.0,
    "roe_min": 0.0, "debt_ratio_max": 80.0, "div_yield_min": 0.0,
    "max_cycle_strength": "mid_weak", "excluded_sw_l2": ["煤炭开采", "石油开采", "工业金属"],
}


def fast_filter(snapshot: List[Dict], params: Dict) -> List[Dict]:
    """盘中快筛. 所有字段用 .get + 安全默认值, 缺失字段不参与淘汰 (永不 KeyError)"""
    out = []
    for raw in snapshot:
        r = _normalize(raw)  # 补齐缺列, 防止后续 r["..."] 抛 KeyError
        # 数值字段: 缺失 -> 用"最宽松"默认值, 让缺失数据不被误杀也不崩溃
        price = r.get("price") or 0.0
        in_out = r.get("in_out_ratio") or 0.0
        ddx1 = r.get("ddx1") or 0.0
        ddx5 = r.get("ddx5") or 0.0
        ddx10 = r.get("ddx10") or 0.0
        ddx20 = r.get("ddx20") or 0.0
        vol_ratio = r.get("vol_ratio") or 0.0
        turn = r.get("turn") or 0.0
        amount = r.get("amount") or 0.0
        circ_mv = r.get("circ_mv") or 0.0
        pb = r.get("pb") or 0.0
        pe_dyn = r.get("pe_dyn") or 0.0
        pe_static = r.get("pe_static") or 0.0
        pe_ttm = r.get("pe_ttm") or 0.0
        profit_yoy = r.get("profit_yoy") or 0.0
        roe = r.get("roe") or 0.0
        debt_ratio = r.get("debt_ratio") or 0.0
        div_yield = r.get("div_yield") or 0.0
        sw_l2 = r.get("sw_l2") or ""
        cycle = r.get("cycle") or "none"

        if not (params["price_max"] >= price >= 0):
            continue
        if in_out >= params["in_out_ratio_max"]:
            continue
        if ddx1 <= params["ddx1_min"]:
            continue
        if ddx5 <= params["ddx5_min"]:
            continue
        if ddx10 <= params["ddx10_min"]:
            continue
        if ddx20 <= params["ddx20_min"]:
            continue
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
        if vol_ratio <= params["vol_ratio_min"]:
            continue
        if turn < params["turn_min"]:
            continue
        if amount < params["amount_min"]:
            continue
        if circ_mv < params["circ_mv_min"]:
            continue
        if not (0 < pb <= params["pb_max"]):
            continue
        if not (0 < pe_dyn <= params["pe_dyn_max"]):
            continue
        if not (0 < pe_static <= params["pe_static_max"]):
            continue
        if not (0 < pe_ttm <= params["pe_ttm_max"]):
            continue
        if pe_dyn / max(pe_static, 1e-9) >= params["pe_dyn_static_ratio_max"]:
            continue
        if pe_dyn / max(pe_ttm, 1e-9) >= params["pe_dyn_ttm_ratio_max"]:
            continue
        if profit_yoy > 0 and pe_dyn / max(profit_yoy, 1e-9) >= params["peg_max"]:
            continue
        if roe <= params["roe_min"]:
            continue
        if debt_ratio >= params["debt_ratio_max"]:
            continue
        if div_yield <= params["div_yield_min"]:
            continue
        strength = STRENGTH_RANK.get(cycle, 0)
        if strength > STRENGTH_RANK.get(params["max_cycle_strength"], 99):
            continue
        if sw_l2 in params.get("excluded_sw_l2", []):
            continue
        out.append(r)
    return out


def diagnose(snapshot: List[Dict], params: Dict) -> Dict[str, int]:
    from collections import defaultdict
    counts = defaultdict(int)
    for raw in snapshot:
        r = _normalize(raw)
        checks = [
            ("股价", params["price_max"] >= (r.get("price") or 0) >= 0),
            ("内外比", (r.get("in_out_ratio") or 0) < params["in_out_ratio_max"]),
            ("当日DDX", (r.get("ddx1") or 0) > params["ddx1_min"]),
            ("5日DDX", (r.get("ddx5") or 0) > params["ddx5_min"]),
            ("10日DDX", (r.get("ddx10") or 0) > params["ddx10_min"]),
            ("20日DDX", (r.get("ddx20") or 0) > params["ddx20_min"]),
            ("当日增仓%自由流通市值", (r.get("main_pos1", 0) or 0) > params.get("main_pos1_free_min", -99)),
            ("5日增仓%自由流通市值", (r.get("main_pos5", 0) or 0) > params.get("main_pos5_free_min", -99)),
            ("10日增仓%自由流通市值", (r.get("main_pos10", 0) or 0) > params.get("main_pos10_free_min", -99)),
            ("20日增仓%自由流通市值", (r.get("main_pos20", 0) or 0) > params.get("main_pos20_free_min", -99)),
            ("当日增仓%总金额", r.get("main_pos1_amt") is None or r["main_pos1_amt"] > params.get("main_pos1_amt_min", -99)),
            ("5日增仓%总金额", r.get("main_pos5_amt") is None or r["main_pos5_amt"] > params.get("main_pos5_amt_min", -99)),
            ("10日增仓%总金额", r.get("main_pos10_amt") is None or r["main_pos10_amt"] > params.get("main_pos10_amt_min", -99)),
            ("20日增仓%总金额", r.get("main_pos20_amt") is None or r["main_pos20_amt"] > params.get("main_pos20_amt_min", -99)),
            ("量比", (r.get("vol_ratio") or 0) > params["vol_ratio_min"]),
            ("换手率", (r.get("turn") or 0) >= params["turn_min"]),
            ("成交金额", (r.get("amount") or 0) >= params["amount_min"]),
            ("流通市值", (r.get("circ_mv") or 0) >= params["circ_mv_min"]),
            ("市净率", 0 < (r.get("pb") or 0) <= params["pb_max"]),
            ("动态PE", 0 < (r.get("pe_dyn") or 0) <= params["pe_dyn_max"]),
            ("静态PE", 0 < (r.get("pe_static") or 0) <= params["pe_static_max"]),
            ("TTM PE", 0 < (r.get("pe_ttm") or 0) <= params["pe_ttm_max"]),
            ("PE动/静", (r.get("pe_dyn") or 0) / max(r.get("pe_static") or 1e-9, 1e-9) < params["pe_dyn_static_ratio_max"]),
            ("PE动/TTM", (r.get("pe_dyn") or 0) / max(r.get("pe_ttm") or 1e-9, 1e-9) < params["pe_dyn_ttm_ratio_max"]),
            ("PEG", (r.get("profit_yoy") or 0) <= 0 or (r.get("pe_dyn") or 0) / max(r.get("profit_yoy") or 1e-9, 1e-9) < params["peg_max"]),
            ("ROE", (r.get("roe") or 0) > params["roe_min"]),
            ("资产负债率", (r.get("debt_ratio") or 0) < params["debt_ratio_max"]),
            ("股息率", (r.get("div_yield") or 0) > params["div_yield_min"]),
            ("周期强度", STRENGTH_RANK.get(r.get("cycle") or "none", 0) <= STRENGTH_RANK.get(params["max_cycle_strength"], 99)),
            ("二级行业排除", (r.get("sw_l2") or "") not in params.get("excluded_sw_l2", [])),
        ]
        for key, ok in checks:
            counts[key] = counts.get(key, 0)
            if not ok:
                counts[key] += 1
    return counts


# ------------------------------------------------------------------
# 格式化 + 样式
# ------------------------------------------------------------------
def fmt_value(col_key: str, val) -> str:
    cfg = COL_MAP[col_key]
    if val is None:
        return ""
    if isinstance(val, (int, float, np.floating)):
        if cfg["decimals"] is not None:
            return f"{val:.{cfg['decimals']}f}"
        return str(int(val))
    return str(val)


def estimate_col_width(chars: int) -> int:
    return int(chars * 8.6 + 12)


# 数值着色 (用于 Styler.map, 返回 CSS)
def _color_num(v):
    if isinstance(v, (int, float)):
        if v > 0:
            return "color:#ff4d4f"
        if v < 0:
            return "color:#0ecb81"
    return ""


NUM_COLOR_COLS = [
    "chg_pct", "chg5", "chg10", "chg20", "chg60", "chg_yy",
    "ddx1", "ddx5", "ddx10", "ddx20",
    "main_pos1", "main_pos1_amt", "main_pos5", "main_pos5_amt",
    "main_pos10", "main_pos10_amt", "main_pos20", "main_pos20_amt",
    "net_super", "net_big", "net_mid", "net_small", "main_flow", "price",
]


# ------------------------------------------------------------------
# Streamlit 页面
# ------------------------------------------------------------------
st.set_page_config(
    page_title="沪深京实时行情筛选器",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
html, body, .stApp { font-size: 15px; }
table { border-collapse: collapse; }
thead th {
    font-size: 15px !important; font-weight: 600; text-align: left !important;
    white-space: nowrap; padding: 2px 4px !important; border-bottom: 1px solid #333; color: #bbb;
}
tbody td { font-size: 15px !important; padding: 1px 4px !important; white-space: nowrap; }
tbody tr:hover { background: rgba(255,255,255,0.06); }
div[data-testid="stDataFrame"] { font-size: 15px; }
</style>
""", unsafe_allow_html=True)


def main():
    # ============ 侧边栏控件 ============
    with st.sidebar:
        st.title("筛选条件")
        debug_on = st.checkbox("显示 Debug 面板", value=DEBUG) if DEBUG else False

        st.subheader("行情")
        price_max = st.number_input("股价小于(元)", 1, 5000, 50)
        in_out_ratio_max = st.number_input("内外比小于", 0.0, 5.0, 3.5, 0.1)
        vol_ratio_min = st.number_input("量比大于", 0.0, 10.0, 0.6, 0.1)
        turn_min = st.number_input("换手率大于%", 0.0, 20.0, 0.33, 0.1)
        amount_min = st.number_input("总金额大于(亿)", 0.0, 1000.0, 0.0, 0.5)

        st.subheader("DDX / 主力增仓%")
        ddx1_min = st.number_input("当日DDX大于", -10.0, 10.0, -1.0, 0.1)
        ddx5_min = st.number_input("5日DDX大于", -10.0, 10.0, -1.0, 0.1)
        ddx10_min = st.number_input("10日DDX大于", -10.0, 10.0, -1.0, 0.1)
        ddx20_min = st.number_input("20日DDX大于", -10.0, 10.0, -1.0, 0.1)
        st.markdown("**主力增仓% — 自由流通市值口径** *(主, 跨市值可比)*")
        main_pos1_free_min = st.slider("当日增仓%自由流通市值大于", -10.0, 10.0, -1.0, 0.1)
        main_pos5_free_min = st.slider("5日增仓%自由流通市值大于", -10.0, 10.0, -1.0, 0.1)
        main_pos10_free_min = st.slider("10日增仓%自由流通市值大于", -10.0, 10.0, -1.0, 0.1)
        main_pos20_free_min = st.slider("20日增仓%自由流通市值大于", -10.0, 10.0, -1.0, 0.1)
        st.markdown("**主力增仓% — 成交额口径** *(辅, 看主力主导力; 开盘未就绪不淘汰)*")
        main_pos1_amt_min = st.slider("当日增仓%总金额大于", -10.0, 10.0, -10.0, 0.1)
        main_pos5_amt_min = st.slider("5日增仓%总金额大于", -10.0, 10.0, -10.0, 0.1)
        main_pos10_amt_min = st.slider("10日增仓%总金额大于", -10.0, 10.0, -10.0, 0.1)
        main_pos20_amt_min = st.slider("20日增仓%总金额大于", -10.0, 10.0, -10.0, 0.1)

        st.subheader("市值 / 估值")
        circ_mv_min = st.number_input("流通市值大于(亿)", 0, 10000, 5)
        pb_max = st.number_input("市净率小于", 0.0, 1000.0, 10.0, 0.5)
        pe_static_max = st.number_input("静态PE小于", 0.0, 10000.0, 10000.0, 1.0)
        pe_ttm_max = st.number_input("TTM PE小于", 0.0, 1000.0, 1000.0, 1.0)
        pe_dyn_max = st.number_input("动态PE小于", 0.0, 500.0, 500.0, 1.0)
        pe_dyn_static_ratio = st.number_input("动态PE/静态PE小于", 0.0, 5.0, 1.0, 0.1)
        pe_dyn_ttm_ratio = st.number_input("动态PE/TTM PE小于", 0.0, 5.0, 1.0, 0.1)

        st.subheader("财务")
        peg_max = st.number_input("PEG小于", 0.0, 10.0, 1.0, 0.1)
        roe_min = st.number_input("ROE%大于", -100.0, 100.0, 0.0, 0.5)
        debt_ratio_max = st.number_input("资产负债率%小于", 0.0, 100.0, 80.0, 1.0)
        div_yield_min = st.number_input("股息率%大于", 0.0, 50.0, 0.0, 0.1)

        st.subheader("周期股过滤")
        max_cycle = st.select_slider(
            "最大允许周期强度",
            options=["none", "weak", "mid_weak", "mid", "mid_strong", "strong"],
            value="mid_weak",
        )
        all_sw_l2 = sorted({s["sw_l2"] for s in make_mock_pool()})
        excluded_l2 = st.multiselect(
            "精细排除 (申万二级行业)",
            options=all_sw_l2,
            default=["煤炭开采", "石油开采", "工业金属"],
        )
        refresh_rate = st.selectbox("刷新间隔", [1, 3, 5, 10, 15, 20, 30], index=3)

    params = {
        "price_max": price_max, "in_out_ratio_max": in_out_ratio_max,
        "vol_ratio_min": vol_ratio_min, "turn_min": turn_min, "amount_min": amount_min,
        "ddx1_min": ddx1_min, "ddx5_min": ddx5_min, "ddx10_min": ddx10_min, "ddx20_min": ddx20_min,
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

    # ============ 会话状态初始化 ============
    if "ds" not in st.session_state:
        st.session_state.ds = build_data_source()
    if "sim" not in st.session_state:
        st.session_state.sim = MarketSimulator(make_mock_pool())
    if "prev" not in st.session_state:
        st.session_state.prev = {}
    if "history" not in st.session_state:
        st.session_state.history = []
    if "order" not in st.session_state:
        st.session_state.order = DEFAULT_ORDER
    if "col_widths" not in st.session_state:
        st.session_state.col_widths = {c["key"]: estimate_col_width(c["width_chars"]) for c in COLUMNS}

    # ============ 顶部状态栏（含加载状态 + 异常捕获）============
    # ★ 关键: 用带超时的加载占位 + try/except 包裹取数, 避免整个 with header 阻塞
    status = st.empty()
    load_err = None
    entered, exited = set(), set()
    pool, snapshot, selected = [], [], []
    t0 = time.time()
    try:
        with status.container():
            c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 2])
            c1.metric("选中条件", f"{len(DEFAULT_ORDER)} 字段")
            c1.text("⏳ 加载慢池...")
            c2.text("⏳ 加载快照...")
            c5.text("⏳ 正在拉取数据...")

        ds = st.session_state.ds

        # ---- 慢池 (盘后用缓存, 此处直接取; 长任务可加 cache) ----
        pool = make_mock_pool()   # 兜底默认
        try:
            real_pool = ds.get_pool()
            if real_pool:
                pool = real_pool
        except Exception as e:
            load_err = f"get_pool 异常: {e}"

        # ---- 快照 ----
        snapshot = None
        try:
            snapshot = ds.snapshot(pool)
        except Exception as e:
            load_err = (load_err + " | " if load_err else "") + f"snapshot 异常: {e}"
        if not snapshot:
            snapshot = st.session_state.sim.snapshot()

        selected = fast_filter(snapshot, params)
        prev_map = st.session_state.prev
        curr_codes = {r["code"] for r in selected}
        prev_codes = set(prev_map.keys())
        entered = curr_codes - prev_codes
        exited = prev_codes - curr_codes

        # ---- 数据来源标签 ----
        src = getattr(ds, "source", "MOCK")
        if src in ("Tushare", "Realtime"):
            src_label = src
        else:
            err = getattr(ds, "error", "") or load_err or "未启用真实数据"
            src_label = f"MOCK · {err[:60]}"

        # ---- 重绘状态栏 (正式内容) ----
        elapsed = (time.time() - t0) * 1000
        with status.container():
            c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 2])
            c1.metric("选中条件", f"{len(DEFAULT_ORDER)} 字段")
            c2.metric("季度慢池", len(pool))
            c3.metric("当前入选", len(selected), delta=f"+{len(entered)}")
            c4.metric("本轮回局", len(exited), delta=f"-{len(exited)}" if exited else None)
            c5.write(
                f"**最后更新**: {datetime.now().strftime('%H:%M:%S')}  ·  "
                f"耗时 {elapsed:.0f}ms  ·  数据: {src_label}"
            )

    except Exception as e:
        # ★ 顶层兜底: 任何未捕获异常都显示在此, 不再让右侧空白
        st.error(f"❌ 数据加载异常 (界面已保护): {type(e).__name__}: {e}")
        with st.expander("完整堆栈 (Debug)"):
            st.code(traceback.format_exc())
        pool, snapshot, selected = [], [], []
        entered, exited = set(), set()

    # ============ 进出局事件流 ============
    for code in entered:
        r = next((x for x in selected if x["code"] == code), None)
        if r:
            st.session_state.history.insert(0, (datetime.now().strftime("%H:%M:%S"), "✅ 进入", f"{code} {r['name']}"))
    for code in exited:
        st.session_state.history.insert(0, (datetime.now().strftime("%H:%M:%S"), "❌ 出局", f"{code} {prev_map.get(code, {}).get('name', '')}"))
    st.session_state.history = st.session_state.history[:50]
    st.session_state.prev = {r["code"]: r for r in selected}

    # ============ 列设置 ============
    with st.expander("列设置: 拖拽排序 / 显隐", expanded=False):
        order = st.multiselect("显示的字段 (按列表顺序)", options=DEFAULT_ORDER, default=st.session_state.order)
        if not order:  # 防御: multiselect 可能返回空/None
            order = list(DEFAULT_ORDER)
        st.session_state.order = order
        for key in order[:8]:
            cfg = COL_MAP[key]
            st.session_state.col_widths[key] = st.slider(
                f"{cfg['label']} 宽度(px)", 30, 300, st.session_state.col_widths[key], key=f"w_{key}"
            )

    # ============ Debug 面板（默认开，可关闭）============
    if DEBUG and debug_on:
        with st.expander("🛠️ Debug 信息 (数据源 / 慢池 / 快照 / 筛选)", expanded=False):
            ds = st.session_state.ds
            st.write({
                "DATASOURCE": os.getenv("DATASOURCE", "realtime"),
                "USE_MANUAL_POOL": os.getenv("USE_MANUAL_POOL", "true"),
                "ds.type": type(ds).__name__,
                "ds.source": getattr(ds, "source", "?"),
                "ds.error": getattr(ds, "error", "") or "(无)",
                "load_err": load_err or "(无)",
                "pool 数量": len(pool),
                "snapshot 数量": len(snapshot) if snapshot else 0,
                "selected 数量": len(selected),
            })
            if snapshot:
                # 展示快照第一条, 检查字段是否齐全
                first = {k: _safe(v) for k, v in snapshot[0].items()}
                st.write("快照首条 (原始):", first)
                # 检查是否缺列
                missing = [c["key"] for c in COLUMNS if c["key"] not in (snapshot[0] if snapshot else {})]
                if missing:
                    st.warning(f"⚠️ 快照缺少字段: {missing}")
                else:
                    st.success("✅ 字段齐全")

    # ============ 主表格（带加载占位 + 安全渲染）============
    placeholder = st.empty()
    if not snapshot:
        placeholder.warning("⚠️ 快照为空: 数据源未返回任何数据。请展开左侧『🛠️ Debug 信息』查看原因。")
    elif not selected:
        # ★ 明确提示: 是"全被筛掉"而非"空白"
        placeholder.warning(f"当前无满足条件的标的 (慢池 {len(pool)} 只 / 快照 {len(snapshot)} 行全部被筛掉), 请放宽条件.")
        diag = diagnose(snapshot, params)
        sorted_diag = sorted(diag.items(), key=lambda x: -x[1])
        top = [(k, v) for k, v in sorted_diag if v > 0][:5]
        if top:
            st.info("💡 **建议放宽以下过严条件:**")
            for k, v in top:
                st.write(f"  · {k}: 淘汰了 {v}/{len(snapshot)} 只")
    else:
        # ---- 安全渲染: 补齐缺列 + 捕获 Styler 异常 ----
        try:
            df = pd.DataFrame([_normalize(r) for r in selected])
            order = st.session_state.get("order", None) or list(DEFAULT_ORDER)
            cols = [c for c in order if c in df.columns]
            df = df[cols]

            styled = df.copy()
            styler = styled.style
            for col in NUM_COLOR_COLS:
                if col in styled.columns:
                    styler = styler.map(_color_num, subset=[col])

            def row_highlight(row):
                if row.get("code") in entered:
                    return ["background-color: rgba(255,77,79,0.15)"] * len(row)
                return [""] * len(row)

            if "code" in styled.columns:
                styler = styler.apply(row_highlight, axis=1)

            fmt_dict = {c["key"]: f"{{:.{c['decimals']}f}}"
                        for c in COLUMNS if c["decimals"] is not None and c["key"] in cols}
            if fmt_dict:
                styler = styler.format(fmt_dict, na_rep="")

            width_css = "<style>"
            for i, key in enumerate(cols):
                w = st.session_state.col_widths.get(key, 80)
                width_css += (f"table th:nth-child({i+1}), table td:nth-child({i+1}) "
                              f"{{ min-width:{w}px; max-width:{w}px; width:{w}px; }}\n")
            width_css += "</style>"
            st.markdown(width_css, unsafe_allow_html=True)

            placeholder.dataframe(styler, use_container_width=True, height=600, hide_index=True)
        except Exception as e:
            placeholder.error(f"❌ 表格渲染异常: {type(e).__name__}: {e}")
            with st.expander("完整堆栈 (Debug)"):
                st.code(traceback.format_exc())
            # 降级: 原始表格, 无样式, 保证至少能看到数据
            st.dataframe(pd.DataFrame([_normalize(r) for r in selected]), use_container_width=True)

    # ============ 进出局日志 + 说明 ============
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
        - **周期股**: 申万行业分级 + 二级精细排除
        - **实时性**: 默认腾讯+AkShare (无需 token); 设为 Tushare 需 token
        - 字段: 小数统一2位; 金额按亿
        """)
        with st.expander("周期强度对照"):
            st.write({
                "strong": "煤炭/有色/石化/化工/钢铁",
                "mid_strong": "建材/建筑/地产",
                "mid": "机械/电力设备/公用事业/交运",
                "mid_weak": "汽车/农林牧渔/贵金属",
                "weak": "银行/食品饮料",
            })

    st.caption(f"💡 启用自动刷新: 安装 `streamlit-autorefresh`, 当前手动刷新请按 F5 / Cmd+R")


if __name__ == "__main__":
    main()
