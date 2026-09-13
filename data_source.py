# -*- coding: utf-8 -*-
"""
可插拔数据源：真实(TuShare) / Mock 模拟，自动降级 + 本地缓存(规避 1次/小时限流)
=====================================================================
设计：
  - 有 TUSHARE_TOKEN 且 tushare 可用 -> use_real=True，尝试取真实数据
  - 取不到(积分不足/限流/异常) -> 自动降级 Mock，并在 ds.error 记录原因
  - 慢池(pool) 缓存 12h，快照(snapshot) 缓存 5min（cache.py）
  - 限流期间：用【过期缓存】兜底，保证界面不断流

公开接口（供 app.py 调用）：
    ds = DataSource(pool=mock_pool_list, use_real=None)  # use_real=None 自动判断
    ds.source        # "Tushare" / "MOCK"
    ds.error         # "" 或降级原因
    ds.get_pool() -> list[dict]      # 季度慢池（财报+估值+市值）
    ds.snapshot(pool) -> list[dict]  # 盘中快照
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
except Exception:
    ts = None

import cache  # 本地缓存


# ---------- 工具 ----------
def _f(v, default=0.0) -> float:
    """安全转 float（处理 None / nan / 空字符串）"""
    try:
        if v is None or v == "" or (isinstance(v, float) and np.isnan(v)):
            return default
        return float(v)
    except Exception:
        return default


def _last_open_days(pro, exchange, start, end, n=1) -> Optional[str]:
    """取最近 n 个交易日的列表（兼容 cal_date / trade_date 列名）"""
    cal = pro.trade_cal(exchange=exchange, start_date=start, end_date=end, is_open="1")
    if cal is None or len(cal) == 0:
        return None
    col = "cal_date" if "cal_date" in cal.columns else "trade_date"
    return sorted(cal[col].tolist())[-n:]


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


# ==================================================================
# Mock 数据源（降级兜底，字段结构与真实源完全一致）
# ==================================================================
class MockDataSource:
    """内置模拟数据，保证任何时候界面都有数据可展示"""

    def __init__(self, pool: list = None):
        self.source = "MOCK"
        self.error = ""
        self._pool = pool or []
        self.tick = 0
        self._rng = np.random.default_rng(42)

    def get_pool(self) -> List[Dict]:
        return self._pool

    def snapshot(self, pool: List[Dict]) -> List[Dict]:
        self.tick += 1
        progress = min(1.0, self.tick / 20.0)
        rows = []
        for s in pool:
            noise = self._rng.normal(0, 0.01)
            price = s["base_price"] * (1 + noise + 0.002 * np.sin(self.tick / 5.0))
            prev = s["base_price"]
            chg = (price / prev - 1) * 100 if prev else 0
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
                "pb": round(s["pb"] * (price / prev), 2),
                "pe_static": round(s["pe_static"], 2),
                "pe_ttm": round(s["pe_ttm"] * (prev / price), 2),
                "pe_dyn": round(s["pe_dyn"] * (prev / price), 2),
            })
        # 主力增仓% 双口径
        for r in rows:
            net1 = _f(r.get("net_super")) + _f(r.get("net_big"))
            net5 = _f(r.get("net_main5"), net1 * 3)
            net10 = _f(r.get("net_main10"), net1 * 6)
            net20 = _f(r.get("net_main20"), net1 * 10)
            free = _f(r.get("free_circ_mv")) or _f(r.get("circ_mv"))
            amt = _f(r.get("amount"))
            for net, kf, ka in [
                (net1, "main_pos1", "main_pos1_amt"),
                (net5, "main_pos5", "main_pos5_amt"),
                (net10, "main_pos10", "main_pos10_amt"),
                (net20, "main_pos20", "main_pos20_amt"),
            ]:
                r[kf] = round(net / free * 100, 2) if free else None
                r[ka] = round(net / amt * 100, 2) if amt else None
        return rows


# ==================================================================
# 真实数据源（TuShare）
# ==================================================================
class TushareDataSource:
    """
    有 token 时自动启用；任何一步失败 -> 降级 Mock + 记录 error。
    字段以 TuShare 实测为准（你的 token 已验证 stock_basic 可用）。
    """

    def __init__(self, pool: list = None, token: str = None, trade_date: str = None):
        self._mock_pool = pool
        self.token = token or os.getenv("TUSHARE_TOKEN", "")
        self.trade_date = trade_date
        self.pro = None
        self.source = "MOCK"
        self.error = ""
        self._mock = MockDataSource(pool=pool)

        if not self.token:
            self.error = "未设置 TUSHARE_TOKEN（.env 中配置）"
            return
        if ts is None:
            self.error = "未安装 tushare（pip install tushare）"
            return

        try:
            ts.set_token(self.token)
            self.pro = ts.pro_api()
            # 探活：1次/小时接口，优先读缓存，避免触发限流
            cached = cache.get_stale("stock_basic")
            if cached is not None:
                self.source = "Tushare"
                return
            sb = self.pro.stock_basic(exchange="", list_status="L",
                                      fields="ts_code,symbol,name,industry,market,list_date", limit=1)
            if sb is None or len(sb) == 0:
                raise RuntimeError("stock_basic 返回 0 行（token 积分/权限不足）")
            self.source = "Tushare"
        except Exception as e:
            self.source = "MOCK"
            self.error = f"tushare 初始化失败：{e}"
            self.pro = None

    # ---------- 慢池（日级，缓存 12h） ----------
    def get_pool(self) -> List[Dict]:
        if self.source != "Tushare":
            return self._mock.get_pool()

        # 优先读缓存（即使过期也先用，避免限流时频繁请求）
        cached = cache.get("pool")
        if cached:
            return cached

        try:
            pool = self._build_pool()
            if pool:
                cache.put("pool", pool)
                return pool
            # 取到了但为空 -> 用过期缓存兜底
            stale = cache.get_stale("pool")
            if stale:
                self.error = "本轮慢池为空，使用过期缓存"
                return stale
        except Exception as e:
            self.error = f"慢池构建失败：{e}"
            stale = cache.get_stale("pool")
            if stale:
                return stale
        return self._mock.get_pool()

    def _build_pool(self) -> List[Dict]:
        pro = self.pro
        # 1) 基础信息（限流：读过期缓存也行）
        basic = cache.get_stale("stock_basic")
        if basic is None:
            basic = pro.stock_basic(exchange="", list_status="L",
                                    fields="ts_code,symbol,name,industry,market,list_date")
            if basic is not None and len(basic) > 0:
                cache.put("stock_basic", basic.to_dict("records"))
        if basic is None or len(basic) == 0:
            raise RuntimeError("stock_basic 返回 0 行（权限/限流）")

        # 2) 最近交易日估值快照
        today = datetime.now()
        start = (today - timedelta(days=90)).strftime("%Y%m%d")
        end = (today + timedelta(days=1)).strftime("%Y%m%d")
        days = _last_open_days(pro, "SSE", start, end, n=1)
        if not days:
            raise RuntimeError("取不到最近交易日（trade_cal 限流/无权限）")
        td = days[0]

        db = pro.daily_basic(trade_date=td, fields=(
            "ts_code,close,pre_close,pe,pe_ttm,pb,turnover_rate,volume_ratio,"
            "total_mv,circ_mv,free_share,amount"
        ))
        if db is None or len(db) == 0:
            raise RuntimeError(f"daily_basic({td}) 返回 0 行（限流/非交易日）")
        db_idx = {r["ts_code"]: r for _, r in db.iterrows()}

        # 3) 财务（低积分会失败，try 降级 -> 用 0 占位，不阻断主流程）
        fin_idx = {}
        try:
            fin = pro.fina_indicator(period=td[:4] + "Q4" if False else None,
                                     fields="ts_code,roe,ordinay_profit_yoy,grossprofit_margin,debt_to_assets,dividend_yield_ratio")
            # 免费积分无权限时直接抛异常 -> 走 except
            if fin is not None and len(fin) > 0:
                for _, r in fin.iterrows():
                    fin_idx[r["ts_code"]] = r
        except Exception as e:
            self.error = f"财务接口降级（{e.__class__.__name__}）"

        # 4) 组装（只保留主板，流通市值>100亿 在 app.py 慢池层再过滤更灵活）
        out = []
        for _, b in basic.iterrows():
            ts_code = b["ts_code"]
            d = db_idx.get(ts_code, {})
            code6 = str(b.get("symbol") or ts_code[:6])
            ind = b.get("industry") or ""
            close = _f(d.get("close"))
            pre = _f(d.get("pre_close"), close) or close
            chg = round((close / pre - 1) * 100, 2) if pre > 0 else 0.0
            free_sh = _f(d.get("free_share"))
            free_mv = free_sh * close / 1e8 if free_sh > 0 else _f(d.get("circ_mv"))
            f = fin_idx.get(ts_code, {})
            out.append({
                "code": code6, "ts_code": ts_code,
                "name": b.get("name") or code6,
                "sw_l1": ind, "sw_l2": ind,
                "cycle": SW_CYCLE.get(ind, "none"),
                # 行情
                "price": close, "chg_pct": chg,
                "vol_ratio": _f(d.get("volume_ratio"), 1.0),
                "turn": _f(d.get("turnover_rate")),
                "amount": _f(d.get("amount")) / 1e8,  # 千元->亿
                # 市值/估值
                "total_mv": _f(d.get("total_mv")) / 1e8,
                "circ_mv": _f(d.get("circ_mv")) / 1e8,
                "free_circ_mv": free_mv,
                "pb": _f(d.get("pb")),
                "pe_static": _f(d.get("pe")),
                "pe_ttm": _f(d.get("pe_ttm")),
                "pe_dyn": _f(d.get("pe_ttm")),  # 无预测EPS，用TTM近似
                # 财务（低积分=0占位）
                "roe": _f(f.get("roe")),
                "profit_yoy": _f(f.get("ordinay_profit_yoy")),
                "rev_yoy": 0.0,
                "gross_margin": _f(f.get("grossprofit_margin")),
                "debt_ratio": _f(f.get("debt_to_assets")),
                "div_yield": _f(f.get("dividend_yield_ratio")) / 100,  # 百分数->小数
                # 资金（快照层补）
                "net_super": 0, "net_big": 0, "net_mid": 0, "net_small": 0,
                "net_main5": 0, "net_main10": 0, "net_main20": 0,
                "ddx1": 0, "in_out_ratio": None,
            })
        return out

    # ---------- 快照（盘中级，缓存 5min） ----------
    def snapshot(self, pool: List[Dict]) -> Optional[List[Dict]]:
        if self.source != "Tushare":
            return self._mock.snapshot(pool)

        cached = cache.get("snapshot")
        if cached:
            return cached
        try:
            snap = self._snapshot(pool)
            if snap:
                cache.put("snapshot", snap)
                return snap
        except Exception as e:
            self.error = f"快照失败：{e}"
        # 失败 -> 过期缓存 / mock
        stale = cache.get_stale("snapshot")
        if stale:
            return stale
        return self._mock.snapshot(pool)

    def _snapshot(self, pool: List[Dict]) -> List[Dict]:
        pro = self.pro
        today = datetime.now()
        start = (today - timedelta(days=90)).strftime("%Y%m%d")
        end = (today + timedelta(days=1)).strftime("%Y%m%d")
        days = _last_open_days(pro, "SSE", start, end, n=1)
        if not days:
            raise RuntimeError("取不到最近交易日")
        td = days[0]

        db = pro.daily_basic(trade_date=td, fields=(
            "ts_code,close,pre_close,pe,pe_ttm,pb,turnover_rate,volume_ratio,"
            "total_mv,circ_mv,free_share,amount"
        ))
        if db is None or len(db) == 0:
            raise RuntimeError(f"daily_basic({td}) 为空")
        db_idx = {r["ts_code"]: r for _, r in db.iterrows()}

        # 资金流（低积分常失败，try 降级 -> DDX/内外比用近似）
        mf_idx = {}
        try:
            mf = pro.moneyflow(trade_date=td)
            if mf is not None and len(mf) > 0:
                for _, r in mf.iterrows():
                    mf_idx[r["ts_code"]] = r
        except Exception as e:
            self.error = f"资金流降级（{e.__class__.__name__}）"

        rows = []
        for p in pool:
            ts_code = p.get("ts_code")
            d = db_idx.get(ts_code, {})
            close = _f(d.get("close")) or _f(p.get("price"))
            pre = _f(d.get("pre_close"), close) or close
            chg = round((close / pre - 1) * 100, 2) if pre > 0 else 0.0
            free_sh = _f(d.get("free_share"))
            free_mv = free_sh * close / 1e8 if free_sh > 0 else _f(d.get("circ_mv"))
            amt = _f(d.get("amount")) / 1e8

            rec = dict(p)
            rec.update({
                "price": close, "chg_pct": chg,
                "vol_ratio": _f(d.get("volume_ratio"), rec.get("vol_ratio", 1.0)),
                "turn": _f(d.get("turnover_rate")),
                "amount": amt,
                "total_mv": _f(d.get("total_mv")) / 1e8,
                "circ_mv": _f(d.get("circ_mv")) / 1e8,
                "free_circ_mv": free_mv,
                "pb": _f(d.get("pb"), rec.get("pb", 0)),
                "pe_static": _f(d.get("pe"), rec.get("pe_static", 0)),
                "pe_ttm": _f(d.get("pe_ttm"), rec.get("pe_ttm", 0)),
                "pe_dyn": _f(d.get("pe_ttm"), rec.get("pe_dyn", 0)),
            })

            m = mf_idx.get(ts_code, {})
            super_net = _f(m.get("buy_elg_amount")) - _f(m.get("sell_elg_amount"))
            big_net = _f(m.get("buy_lg_amount")) - _f(m.get("sell_lg_amount"))
            mid_net = _f(m.get("buy_md_amount")) - _f(m.get("sell_md_amount"))
            small_net = _f(m.get("buy_sm_amount")) - _f(m.get("sell_sm_amount"))
            rec["net_super"] = round(super_net / 1e8, 2)
            rec["net_big"] = round(big_net / 1e8, 2)
            rec["net_mid"] = round(mid_net / 1e8, 2)
            rec["net_small"] = round(small_net / 1e8, 2)

            # 内外比：moneyflow 无内外盘，用主动买卖量近似（低积分=None）
            buy_vol = sum(_f(m.get(k)) for k in
                          ["buy_elg_vol", "buy_lg_vol", "buy_md_vol", "buy_sm_vol"])
            sell_vol = sum(_f(m.get(k)) for k in
                           ["sell_elg_vol", "sell_lg_vol", "sell_md_vol", "sell_sm_vol"])
            rec["in_out_ratio"] = round(buy_vol / sell_vol, 2) if sell_vol > 0 else None

            # DDX：接口无则近似
            rec["ddx1"] = _f(m.get("ddx")) or round(big_net / 1e8 / max(free_mv, 1), 2) if free_mv else 0.0

            # ---- 主力增仓% 双口径（真实公式）----
            main_net = super_net + big_net  # 万元
            rec["main_pos1"] = round(main_net / 1e8 / max(free_mv, 1e-6) * 100, 2) if free_mv else None
            rec["main_pos1_amt"] = round(main_net / 1e8 / max(amt, 1e-6) * 100, 2) if amt else None
            # 5/10/20 日：日频快照无历史，暂留 None（后续按股回看补充）
            rec["main_pos5"] = None; rec["main_pos5_amt"] = None
            rec["main_pos10"] = None; rec["main_pos10_amt"] = None
            rec["main_pos20"] = None; rec["main_pos20_amt"] = None
            rows.append(rec)
        return rows


# ==================================================================
# 统一入口（app.py 只用这一个类）
# ==================================================================
class DataSource:
    """
    根据环境自动选择真实/Mock：
        DataSource(pool=make_mock_pool(), use_real=None)
        - use_real=None（默认）：有 token 且 tushare 可用 -> 真实，否则 Mock
        - use_real=True  ：强制真实（无 token 也会降级 Mock 并记录 error）
        - use_real=False ：强制 Mock（离线/调试用）
    对外接口：source / error / get_pool() / snapshot(pool)
    """

    def __init__(self, pool: list = None, token: str = None, use_real: Optional[bool] = None):
        self._mock_pool = pool
        self.token = token or os.getenv("TUSHARE_TOKEN", "")
        self.error = ""

        if use_real is False:
            self._impl = MockDataSource(pool=pool)
            self.source = "MOCK"
            return

        # use_real=None -> 自动判断；True -> 强制尝试
        real = TushareDataSource(pool=pool, token=self.token)
        if real.source == "Tushare" and (use_real is True or bool(self.token)):
            self._impl = real
            self.source = "Tushare"
        else:
            self._impl = MockDataSource(pool=pool)
            self.source = "MOCK"
            self.error = real.error or "自动降级 Mock"

    @property
    def mode(self) -> str:
        return self.source

    def get_pool(self) -> List[Dict]:
        return self._impl.get_pool()

    def snapshot(self, pool: List[Dict]) -> List[Dict]:
        return self._impl.snapshot(pool)


# ==================== 独立测试 ====================
if __name__ == "__main__":
    print("TUSHARE_TOKEN loaded:", bool(os.getenv("TUSHARE_TOKEN")))
    ds = DataSource(use_real=None)
    print("mode:", ds.source, "| error:", ds.error)
    pool = ds.get_pool()
    print("慢池数量:", len(pool))
    if pool:
        print("样例:", pool[0])
    snap = ds.snapshot(pool[:20])
    print("快照数量:", len(snap) if snap else 0)
    if snap:
        print("快照首行:", snap[0])
