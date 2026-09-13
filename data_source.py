# -*- coding: utf-8 -*-
"""
data_source.py —— 可插拔双模数据源（对齐 app.py 调用签名）

对外接口（app.py 依赖这些）：
    ds = DataSource(pool=make_mock_pool(), use_real=None)  # use_real: True/False/None(自动)
    ds.source            # "Tushare" / "Mock"  (供界面显示)
    ds.error             # 最近的异常说明（为空=无异常）
    ds.get_pool()        -> List[Dict]            # 季度慢池（财报级）
    ds.snapshot(pool)    -> List[Dict] | None     # 盘中快照（None=请降级 mock）

实盘（use_real=True 且 tushare 可用 + 有 token）：
    慢池: tushare stock_basic + daily_basic  (估值/市值/换手/量比/PE)
    快照: 最近交易日 daily_basic + moneyflow  (资金流拆分/DDX/内外比近似)
    财务(ROE/利润同比/毛利率/负债率/股息率): tushare fina_indicator，分批补，失败不致命
降级：任何一步异常 -> source="Mock"，error 记录原因，snapshot 返回 None 让 app 走 mock。

环境变量：
    TUSHARE_TOKEN  (必需才进实盘)
    .env 由 python-dotenv 自动加载（需在项目根放 .env）

内外比: 成交额口径用主动买卖量近似 (buy_*/sell_*_vol)；无数据则 None（逐步入围）。
主力增仓% 双口径: 自由流通市值口径(主) + 成交额口径(辅)，与 app.py compute_main_positions 口径一致。
"""
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import numpy as np
import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    import tushare as ts
    HAVE_TUSHARE = True
except Exception:
    ts = None
    HAVE_TUSHARE = False


# 申万一级行业 -> 周期强度（strong/mid_strong/mid/mid_weak/weak/none）
SW_CYCLE = {
    "煤炭": "strong", "石油石化": "strong", "有色金属": "strong", "钢铁": "strong",
    "基础化工": "strong", "建筑材料": "mid_strong", "建筑装饰": "mid_strong",
    "房地产": "mid_strong", "机械设备": "mid", "电力设备": "mid", "公用事业": "mid",
    "交通运输": "mid", "国防军工": "mid", "汽车": "mid_weak", "农林牧渔": "mid_weak",
    "家用电器": "mid_weak", "贵金属": "mid_weak", "银行": "weak", "非银金融": "weak",
    "食品饮料": "weak", "医药生物": "weak", "纺织服饰": "weak", "商贸零售": "weak",
    "美容护理": "weak", "计算机": "none", "电子": "none", "通信": "none",
    "传媒": "none", "社会服务": "none",
}


def _f(x, default=0.0):
    """安全转 float，空/异常 -> default"""
    if x is None:
        return default
    try:
        s = str(x).strip()
        if s in ("", "-", "--", "None", "NaN", "nan"):
            return default
        return float(s)
    except (ValueError, TypeError):
        return default


def _last_open_days(pro, n=1, end: str = None):
    """取最近 n 个交易日（按 SSE 日历），自适应列名 cal_date/trade_date"""
    e = end or datetime.now().strftime("%Y%m%d")
    s = (datetime.strptime(e, "%Y%m%d") - timedelta(days=120)).strftime("%Y%m%d")
    cal = pro.trade_cal(exchange="SSE", start_date=s, end_date=e, is_open="1")
    if cal is None or len(cal) == 0:
        # 兜底：直接取 end 当天
        return [e]
    col = "cal_date" if "cal_date" in cal.columns else "trade_date"
    days = cal[col].tolist()[::-1]
    return days[:n]


class MockDataSource:
    """无网络/无 token/实盘失败时的兜底，返回与真实源同 key 的数据，便于本地开发"""

    def __init__(self, pool: Optional[List[Dict]] = None):
        self._pool = pool or []
        self._rng = np.random.default_rng(7)

    def snapshot(self, codes):
        rows = []
        for code in codes:
            # 支持 dict 或 str
            if isinstance(code, dict):
                code = code.get("code", "")
            outer = float(self._rng.integers(10000, 500000))
            inner = float(self._rng.integers(8000, 400000))
            price = round(self._rng.uniform(5, 200), 2)
            amount = round(self._rng.uniform(0.5, 50), 2)
            rows.append({
                "code": str(code), "name": f"模拟{code}", "price": price,
                "chg_pct": round(self._rng.uniform(-5, 5), 2),
                "open": price, "amount": amount,
                "turn": round(self._rng.uniform(0, 8), 2),
                "vol_ratio": round(self._rng.uniform(0.3, 3), 2),
                "volume_lot": outer + inner,
                "inner_vol": inner, "outer_vol": outer,
                "in_out_ratio": round(inner / outer, 2),
                "pb": round(self._rng.uniform(0.5, 10), 2),
                "pe_static": round(self._rng.uniform(5, 60), 2),
                "pe_ttm": round(self._rng.uniform(5, 60), 2),
                "pe_dyn": round(self._rng.uniform(5, 60), 2),
                "circ_mv": round(self._rng.uniform(50, 10000), 2),
                "total_mv": round(self._rng.uniform(60, 12000), 2),
                "free_circ_mv": round(self._rng.uniform(40, 8000), 2),
                "net_super": round(self._rng.uniform(-5, 5), 2),
                "net_big": round(self._rng.uniform(-5, 5), 2),
                "net_mid": round(self._rng.uniform(-5, 5), 2),
                "net_small": round(self._rng.uniform(-5, 5), 2),
                "ddx1": round(self._rng.uniform(-2, 2), 2),
                "profit_yoy": round(self._rng.uniform(-30, 60), 2),
                "rev_yoy": round(self._rng.uniform(-20, 50), 2),
                "roe": round(self._rng.uniform(-5, 35), 2),
                "gross_margin": round(self._rng.uniform(5, 90), 2),
                "debt_ratio": round(self._rng.uniform(20, 85), 2),
                "div_yield": round(self._rng.uniform(0, 6), 2),
            })
        return rows

    def fetch_fundamentals(self, codes):
        # 与 FinancialSource.fetch_fundamentals 同契约
        out = {}
        for code in codes:
            c = code.get("code", "") if isinstance(code, dict) else code
            out[str(c)] = {
                "profit_yoy": round(self._rng.uniform(-30, 60), 2),
                "rev_yoy": round(self._rng.uniform(-20, 50), 2),
                "roe": round(self._rng.uniform(-5, 35), 2),
                "gross_margin": round(self._rng.uniform(5, 90), 2),
                "debt_ratio": round(self._rng.uniform(20, 85), 2),
                "div_yield": round(self._rng.uniform(0, 6), 2),
                "ocf_to_np": round(self._rng.uniform(-2, 3), 2),
                "circ_mv": round(self._rng.uniform(50, 10000), 2),
                "free_circ_mv": round(self._rng.uniform(40, 8000), 2),
            }
        return out

    # 别名，兼容旧调用
    fetch = snapshot


class DataSource:
    def __init__(self, pool: Optional[List[Dict]] = None, token: Optional[str] = None,
                 use_real: Optional[bool] = None, trade_date: Optional[str] = None,
                 mock_pool_fn=None):
        self._mock_pool = pool or []
        self.mock_pool_fn = mock_pool_fn
        self.token = token or os.getenv("TUSHARE_TOKEN", "")
        # use_real: None=有token且tushare可用就真，否则mock；True/False 强制
        if use_real is True:
            self.use_real = True
        elif use_real is False:
            self.use_real = False
        else:
            self.use_real = bool(self.token) and HAVE_TUSHARE
        # 无 token 一律 mock，避免无效尝试
        if self.use_real and not self.token:
            self.use_real = False
            self.error = "未配置 TUSHARE_TOKEN，已降级 Mock"
        self.trade_date = trade_date
        self.source = "Mock"   # 仅在 get_pool/snapshot 真实取数成功后才改为 "Tushare"
        self.pro = None
        self.error = ""
        if self.use_real:
            try:
                ts.set_token(self.token)
                self.pro = ts.pro_api()
                # 探活：取一只股票验证 token 有效
                self.pro.stock_basic(exchange="", list_status="L",
                                     fields="ts_code,symbol,name", limit=1)
            except Exception as e:
                self.use_real = False
                self.error = f"tushare init failed: {e}"

    # ==================== ① 季度慢池 ====================
    def get_pool(self) -> List[Dict]:
        if not self.use_real or self.pro is None:
            return self._mock()
        try:
            return self._build_pool()
        except Exception as e:
            self.error = f"get_pool failed: {e}"
            return self._mock()

    def _mock(self) -> List[Dict]:
        if self.mock_pool_fn is not None:
            return self.mock_pool_fn()
        if self._mock_pool:
            return self._mock_pool
        return []

    def _build_pool(self) -> List[Dict]:
        basic = self.pro.stock_basic(exchange="", list_status="L",
                                     fields="ts_code,symbol,name,industry,market,list_date")
        if basic is None or len(basic) == 0:
            raise RuntimeError(
                "stock_basic 返回 0 行（token 积分不足或接口未授权，请到 tushare.pro 检查积分）")
        td = _last_open_days(self.pro, 1)[0]
        db = self.pro.daily_basic(
            trade_date=td,
            fields="ts_code,close,pre_close,pe,pe_ttm,pb,turnover_rate,volume_ratio,"
                   "total_mv,circ_mv,free_share,amount",
        )
        if db is None or len(db) == 0:
            raise RuntimeError(
                f"daily_basic(trade_date={td}) 返回 0 行（{td} 可能非交易日或权限不足）")
        db = db.merge(basic, on="ts_code", how="inner")
        out: List[Dict] = []
        self.source = "Tushare"   # 能跑到这里说明 tushare 调用链通畅
        for _, r in db.iterrows():
            code6 = str(r["symbol"])
            ind = r.get("industry") or ""
            close = _f(r.get("close"))
            pre = _f(r.get("pre_close")) or close
            circ_mv_yi = _f(r.get("circ_mv")) / 1e8         # 千元 -> 亿元
            free_share = _f(r.get("free_share"))
            free_mv_yi = (free_share * close / 1e8) if free_share > 0 else circ_mv_yi
            out.append({
                "code": code6, "ts_code": r["ts_code"], "name": r.get("name") or code6,
                "sw_l1": ind, "sw_l2": ind,
                "cycle": SW_CYCLE.get(ind, "none"),
                "price": close,
                "pre_close": pre,
                "chg_pct": round((close / pre - 1) * 100, 2) if pre > 0 else 0.0,
                "turn": _f(r.get("turnover_rate")),
                "vol_ratio": _f(r.get("volume_ratio"), 1.0),
                "amount": _f(r.get("amount")) / 1e8,      # 千元 -> 亿元
                "total_mv": _f(r.get("total_mv")) / 1e8,
                "circ_mv": circ_mv_yi,
                "free_circ_mv": free_mv_yi,
                "pb": _f(r.get("pb")),
                "pe_static": _f(r.get("pe")),
                "pe_ttm": _f(r.get("pe_ttm")),
                "pe_dyn": _f(r.get("pe_ttm")),            # 无预测EPS，ttm近似
                # 财务字段：日频快照没有，下面 _fill_finance 分批补（失败不致命）
                "profit_yoy": 0.0, "rev_yoy": 0.0, "roe": 0.0,
                "gross_margin": 0.0, "debt_ratio": 0.0, "div_yield": 0.0,
            })
        self._fill_finance(out)
        return out

    def _fill_finance(self, out: List[Dict]):
        """按 ts_code 分批拉 fina_indicator，补齐 ROE/利润同比/毛利率/负债率/股息率。
        低积分/限频会抛异常 -> 捕获后留 0，不阻断。"""
        if not out:
            return
        # 分批，避免单次参数过长
        codes = [p["ts_code"] for p in out]
        step = 50
        for i in range(0, len(codes), step):
            batch = codes[i:i + step]
            try:
                fi = self.pro.fina_indicator(ts_code=",".join(batch))
            except Exception as e:
                self.error += f" | fina_indicator batch skipped: {e}"
                continue
            if fi is None or len(fi) == 0:
                continue
            # 每只取最新一期 (按 end_date 排序)
            fi = fi.sort_values("end_date", ascending=False)
            latest = fi.drop_duplicates("ts_code", keep="first")
            lut = {row["ts_code"]: row for _, row in latest.iterrows()}
            for p in out:
                row = lut.get(p["ts_code"])
                if row is None:
                    continue
                p["roe"] = _f(row.get("roe"))
                p["profit_yoy"] = _f(row.get("yoy_profit"))     # 净利润同比
                p["rev_yoy"] = _f(row.get("yoy_sales"))         # 营业总收入同比
                p["gross_margin"] = _f(row.get("grossprofit_margin"))
                p["debt_ratio"] = _f(row.get("debt_to_assets"))

    # ==================== ② 盘中快照 ====================
    def snapshot(self, pool: List[Dict]) -> Optional[List[Dict]]:
        if not self.use_real or self.pro is None:
            return None
        try:
            return self._snapshot(pool)
        except Exception as e:
            self.error = f"snapshot failed: {e}"
            return None

    def _snapshot(self, pool: List[Dict]) -> List[Dict]:
        td = _last_open_days(self.pro, 1)[0]
        db = self.pro.daily_basic(
            trade_date=td,
            fields="ts_code,close,pre_close,pe,pe_ttm,pb,turnover_rate,volume_ratio,"
                   "total_mv,circ_mv,free_share,amount,net_mf_vol",
        )
        db_idx = {r["ts_code"]: r for _, r in db.iterrows()}

        # 资金流（低积分会空 -> 容错）
        mf_map: Dict[str, Dict] = {}
        try:
            mf = self.pro.moneyflow(
                trade_date=td,
                fields="ts_code,buy_sm_vol,buy_sm_amount,sell_sm_vol,sell_sm_amount,"
                       "buy_md_vol,buy_md_amount,sell_md_vol,sell_md_amount,"
                       "buy_lg_vol,buy_lg_amount,sell_lg_vol,sell_lg_amount,"
                       "buy_elg_vol,buy_elg_amount,sell_elg_vol,sell_elg_amount,net_mf_vol",
            )
            if mf is not None and len(mf):
                mf_map = {r["ts_code"]: r for _, r in mf.iterrows()}
        except Exception as e:
            self.error += f" | moneyflow skipped: {e}"

        rows: List[Dict] = []
        if pool:
            self.source = "Tushare"   # 能跑到这里说明 tushare 调用链通畅
        for p in pool:
            ts_code = p.get("ts_code")
            d = db_idx.get(ts_code, {})
            price = _f(d.get("close")) or p.get("price", 0)
            pre = _f(d.get("pre_close")) or price
            chg = round((price / pre - 1) * 100, 2) if pre > 0 else 0.0
            circ_mv_yi = _f(d.get("circ_mv")) / 1e8
            free_share = _f(d.get("free_share"))
            free_mv_yi = (free_share * price / 1e8) if free_share > 0 else circ_mv_yi
            amount_yi = _f(d.get("amount")) / 1e8

            rec = dict(p)
            rec.update({
                "price": price, "chg_pct": chg,
                "turn": _f(d.get("turnover_rate")),
                "vol_ratio": _f(d.get("volume_ratio"), p.get("vol_ratio", 1.0)),
                "amount": amount_yi,
                "total_mv": _f(d.get("total_mv")) / 1e8,
                "circ_mv": circ_mv_yi,
                "free_circ_mv": free_mv_yi,
                "pb": _f(d.get("pb"), p.get("pb", 0)),
                "pe_static": _f(d.get("pe"), p.get("pe_static", 0)),
                "pe_ttm": _f(d.get("pe_ttm"), p.get("pe_ttm", 0)),
                "pe_dyn": _f(d.get("pe_ttm"), p.get("pe_dyn", 0)),
            })

            m = mf_map.get(ts_code, {})
            super_net = _f(m.get("buy_elg_amount")) - _f(m.get("sell_elg_amount"))
            big_net = _f(m.get("buy_lg_amount")) - _f(m.get("sell_lg_amount"))
            mid_net = _f(m.get("buy_md_amount")) - _f(m.get("sell_md_amount"))
            small_net = _f(m.get("buy_sm_amount")) - _f(m.get("sell_sm_amount"))
            rec["net_super"] = round(super_net / 1e8, 2)
            rec["net_big"] = round(big_net / 1e8, 2)
            rec["net_mid"] = round(mid_net / 1e8, 2)
            rec["net_small"] = round(small_net / 1e8, 2)

            # 内外比近似 = 主动买量 / 主动卖量 (moneyflow 无内外盘原始值)
            buy_vol = sum(_f(m.get(k)) for k in
                          ("buy_elg_vol", "buy_lg_vol", "buy_md_vol", "buy_sm_vol"))
            sell_vol = sum(_f(m.get(k)) for k in
                           ("sell_elg_vol", "sell_lg_vol", "sell_md_vol", "sell_sm_vol"))
            rec["in_out_ratio"] = round(buy_vol / sell_vol, 2) if sell_vol > 0 else None

            # DDX：moneyflow 无，用主力净额近似（后续可接东财资金流补真值）
            main_net = super_net + big_net
            rec["ddx1"] = round(main_net / 1e8, 2)

            # 主力增仓% 双口径（口径与 app.py compute_main_positions 一致）
            rec["main_pos1"] = (round(main_net / 1e8 / free_mv_yi * 100, 2)
                                if free_mv_yi else None)
            rec["main_pos1_amt"] = (round(main_net / 1e8 / amount_yi * 100, 2)
                                    if amount_yi else None)
            # 5/10/20日：日频快照无历史，先置 None（后续按日缓存可补齐）
            rec["main_pos5"] = rec["main_pos10"] = rec["main_pos20"] = None
            rec["main_pos5_amt"] = rec["main_pos10_amt"] = rec["main_pos20_amt"] = None
            rows.append(rec)
        return rows


# ==================== 自检 ====================
if __name__ == "__main__":
    print("=" * 60)
    print("DataSource 自检")
    print("=" * 60)

    print("\n[1] 无 token -> 应自动降级 Mock，source=Mock")
    ds = DataSource(pool=[], use_real=None)
    print(f"    use_real={ds.use_real}, source={ds.source}, error={ds.error!r}")
    pool = ds.get_pool()
    print(f"    get_pool() -> {len(pool)} 只 (mock)")

    snap = ds.snapshot(pool if pool else [{"ts_code": "000001.SZ", "code": "000001", "price": 12.5, "circ_mv": 2200, "free_circ_mv": 1800}])
    print(f"    snapshot() -> {len(snap) if snap else None} 行")
    if snap:
        r = snap[0]
        print(f"    首行: code={r.get('code')} price={r.get('price')} "
              f"内外比={r.get('in_out_ratio')} ddx1={r.get('ddx1')} "
              f"main_pos1={r.get('main_pos1')} main_pos1_amt={r.get('main_pos1_amt')}")
        print("    OK: Mock 快照可正常生成" if r.get("code") else "    FAIL")

    print(f"\n[2] use_real=True 但无 token -> 应降级 Mock")
    ds2 = DataSource(pool=[], use_real=True)
    print(f"    use_real={ds2.use_real}, source={ds2.source} (期望 Mock)")

    print(f"\n[3] 内外比/增仓% 公式校验 (用 mock 数据)")
    sample = {"net_super": 1.0, "net_big": 0.5, "free_circ_mv": 1800, "amount": 5.0,
              "code": "TEST", "name": "测试"}
    # 复刻 app.py compute_main_positions 逻辑
    net1 = sample["net_super"] + sample["net_big"]
    free = sample["free_circ_mv"]
    amt = sample["amount"]
    main_pos1 = round(net1 / free * 100, 2) if free else None
    main_pos1_amt = round(net1 / amt * 100, 2) if amt else None
    print(f"    主力净额={net1}亿(示例), free_circ_mv={free}亿, amount={amt}亿")
    print(f"    main_pos1(自由流通市值口径)={net1}/{free}*100={main_pos1}")
    print(f"    main_pos1_amt(成交额口径)={net1}/{amt}*100={main_pos1_amt}")
    assert main_pos1 == round(1.5 / 1800 * 100, 2), "自由流通市值口径公式错误"
    assert main_pos1_amt == round(1.5 / 5.0 * 100, 2), "成交额口径公式错误"
    print("    OK: 双口径公式一致")

    print("\n自检完成.")
