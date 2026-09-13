# -*- coding: utf-8 -*-
"""
TuShare 接口权限诊断（本地运行：python test_ts.py）
==============================================
逐接口测试你的 token 权限，帮你判断"为什么还是 MOCK"。

输出示例：
    TUSHARE_TOKEN loaded: True
    [1] stock_basic: OK (5000+ rows)
    [2] trade_cal: OK
    [3] daily_basic: OK
    [4] moneyflow: 空（降级）
    [5] fina_indicator: 异常（降级）

安装：pip install python-dotenv tushare pandas
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_OK = True
except Exception:
    DOTENV_OK = False

import tushare as ts

TOKEN = os.getenv("TUSHARE_TOKEN", "")
print("python-dotenv available:", DOTENV_OK)
print("TUSHARE_TOKEN loaded:", bool(TOKEN), f"(长度 {len(TOKEN)})" if TOKEN else "")

if not TOKEN:
    print("\n⚠️ 未检测到 TUSHARE_TOKEN，请检查 .env 文件")
    raise SystemExit(1)

ts.set_token(TOKEN)
pro = ts.pro_api()

results = {}


def step(name):
    def deco(fn):
        def wrapper():
            try:
                v = fn()
                results[name] = v
                print(f"  ✓ {name}: {v}")
            except Exception as e:
                results[name] = f"异常: {e}"
                print(f"  ✗ {name}: {e}")
        return wrapper
    return deco


@step("stock_basic（股票列表，一切基础）")
def t1():
    df = pro.stock_basic(exchange="", list_status="L",
                         fields="ts_code,symbol,name,industry,market,list_date")
    if df is None or len(df) == 0:
        return "0 行（积分不足/无权限）"
    return f"OK ({len(df)} rows)"


@step("trade_cal（交易日历，慢池取最近交易日）")
def t2():
    import datetime
    end = datetime.datetime.now().strftime("%Y%m%d")
    start = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y%m%d")
    df = pro.trade_cal(exchange="SSE", start_date=start, end_date=end, is_open="1")
    if df is None or len(df) == 0:
        return "0 行"
    col = "cal_date" if "cal_date" in df.columns else "trade_date"
    return f"OK, 最近交易日 = {sorted(df[col].tolist())[-1]}"


@step("daily_basic（估值/市值/换手/量比，慢池核心）")
def t3():
    import datetime
    end = datetime.datetime.now().strftime("%Y%m%d")
    start = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime("%Y%m%d")
    cal = pro.trade_cal(exchange="SSE", start_date=start, end_date=end, is_open="1")
    col = "cal_date" if "cal_date" in cal.columns else "trade_date"
    td = sorted(cal[col].tolist())[-1]
    df = pro.daily_basic(trade_date=td, fields="ts_code,close,pe,pe_ttm,pb,total_mv,circ_mv,free_share")
    return f"OK ({len(df)} rows, trade_date={td})" if len(df) > 0 else "0 行（限流/非交易日）"


@step("moneyflow（大单净额，内外比/DDX 近似）")
def t4():
    import datetime
    end = datetime.datetime.now().strftime("%Y%m%d")
    start = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime("%Y%m%d")
    cal = pro.trade_cal(exchange="SSE", start_date=start, end_date=end, is_open="1")
    col = "cal_date" if "cal_date" in cal.columns else "trade_date"
    td = sorted(cal[col].tolist())[-1]
    df = pro.moneyflow(trade_date=td)
    return f"OK ({len(df)} rows)" if df is not None and len(df) > 0 else "空（低积分，将降级近似）"


@step("fina_indicator（财务：ROE/利润同比，慢池补全）")
def t5():
    df = pro.fina_indicator(period=None, fields="ts_code,roe,ordinay_profit_yoy", limit=5)
    return f"OK ({len(df)} rows)" if df is not None and len(df) > 0 else "空（低积分，将降级 0 占位）"


print("\n逐项检测：\n")
for fn in (t1, t2, t3, t4, t5):
    fn()

print("\n" + "=" * 50)
print("诊断结论：")
print("  - stock_basic = 0 行  →  token 积分不足，几乎所有接口都会被限")
print("  - daily_basic OK      →  慢池可用，实盘主流程可跑")
print("  - moneyflow/fina 空   →  属正常降级，不影响主流程（字段占位）")
print("  - 频率超限(1次/小时)  →  等待限流窗口，或用 .cache/ 过期缓存兜底")
print("=" * 50)
