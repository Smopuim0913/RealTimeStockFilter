# -*- coding: utf-8 -*-
"""TuShare 真实链路探测（健壮版：逐接口 try/except + 列名自适应）"""
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv(".env.test")
print("TUSHARE_TOKEN loaded:", bool(os.getenv("TUSHARE_TOKEN")))

import tushare as ts
pro = ts.pro_api()


def col(df, *names):
    """自适应列名：返回第一个存在的列"""
    if df is None or len(df) == 0:
        return None
    for n in names:
        if n in df.columns:
            return df[n].tolist()
    return None


def probe(name, fn):
    try:
        df = fn()
        if df is None:
            print(f"[{name}] None 返回（接口未授权/参数为空）")
            return None
        if len(df) == 0:
            print(f"[{name}] 返回 0 行（空）")
            return df
        print(f"[{name}] OK, {len(df)} 行")
        return df
    except Exception as e:
        msg = str(e)
        if "积分" in msg or "积分" in msg.lower():
            print(f"[{name}] 权限/积分不足: {msg[:120]}")
        else:
            print(f"[{name}] 异常: {msg[:160]}")
        return None


# 1) stock_basic
basic = probe("[1] stock_basic", lambda: pro.stock_basic(
    exchange="", list_status="L", fields="ts_code,symbol,name,industry,market,list_date"))

# 2) trade_cal：自适应列名取最近交易日
cal = probe("[2] trade_cal", lambda: pro.trade_cal(
    exchange="SSE",
    start_date=(datetime.now() - timedelta(days=60)).strftime("%Y%m%d"),
    end_date=datetime.now().strftime("%Y%m%d"), is_open="1"))
last_day = None
if cal is not None and len(cal):
    dates = col(cal, "cal_date", "trade_date")
    if dates:
        last_day = dates[0] if dates[0] > dates[-1] else dates[-1]  # 取最大=最近
        # 上面逻辑简单化：直接排序取最大
        last_day = str(max(int(d) for d in dates))
print(f"    -> 最近交易日: {last_day}")

# 3) daily_basic（慢池核心）
db = None
if last_day:
    db = probe("[3] daily_basic (慢池核心)", lambda: pro.daily_basic(
        trade_date=last_day,
        fields="ts_code,close,pre_close,pe,pe_ttm,pb,turnover_rate,volume_ratio,total_mv,circ_mv,free_share,amount"))
    if db is not None and len(db):
        print("    样例:", {k: db.iloc[0][k] for k in db.columns if k in
                           ["ts_code", "close", "pe_ttm", "circ_mv", "free_share"]})

# 4) moneyflow（资金流/DDX，低积分会空）
if last_day:
    probe("[4] moneyflow (资金流/DDX)", lambda: pro.moneyflow(
        trade_date=last_day, fields="ts_code,buy_elg_amount,sell_elg_amount,net_mf_vol"))

# 5) fina_indicator（财务 ROE/利润同比，需积分）
probe("[5] fina_indicator (财务)", lambda: pro.fina_indicator(
    ts_code="000001.SZ", fields="ts_code,end_date,roe,yoy_profit,yoy_sales,grossprofit_margin,debt_to_assets"))

print("\n" + "=" * 50)
print("诊断结论:")
print("  - 若 [1] stock_basic 返回 0 行 -> token 积分不足，几乎所有接口都会被限")
print("  - 若 [3] daily_basic OK -> 慢池可用；否则实盘不可用")
print("  - [4][5] 空/异常属正常降级（低积分），不影响主流程")
print("=" * 50)
