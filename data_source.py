"""
可插拔数据源：真实行情(akshare/tushare) 与 Mock 模拟自动切换
=================================================================
用法（在 app.py 里）：
    from data_source import DataSource
    ds = DataSource(pool=mock_pool)   # mock_pool = make_mock_pool()
    pool   = ds.get_pool()            # 对应 make_mock_pool()  → 季度慢池
    snapshot = ds.snapshot()          # 对应 sim.snapshot()     → 每轮盘中快照

切换开关（环境变量）：
    USE_REAL_DATA=True       启用真实数据（默认 False = 用 MOCK）
    TUSHARE_TOKEN=xxx         tushare Pro 的 token（财报字段需要）
"""

import os
import time
import numpy as np
import pandas as pd

try:
    import akshare as ak
    _HAS_AK = True
except ImportError:
    _HAS_AK = False

try:
    import tushare as ts
    _HAS_TS = True
except ImportError:
    _HAS_TS = False


class DataSource:
    def __init__(self, pool: list = None, tick_seconds: int = 3):
        self._mock_pool = pool or []
        self.use_real = os.getenv("USE_REAL_DATA", "False").lower() in ("true", "1", "yes")
        self.token = os.getenv("TUSHARE_TOKEN", "")
        self.tick = 0
        self.tick_seconds = tick_seconds
        self._rng = np.random.default_rng(42)
        self._last_spot = None      # 缓存上一次快照（盘口波动用）
        self._ts_pro = None

        if self.use_real:
            missing = []
            if not _HAS_AK:
                missing.append("akshare")
            if not _HAS_TS:
                missing.append("tushare")
            if missing:
                print(f"[data_source] 已设置 USE_REAL_DATA=True 但未安装 {missing}，自动降级 MOCK")
                self.use_real = False
            elif not self.token:
                print("[data_source] 警告：未设置 TUSHARE_TOKEN，财报慢变量将为 None，行情仍走真实")
        else:
            print("[data_source] 当前为 MOCK 模拟数据（设 USE_REAL_DATA=True 切换真实）")

    # ==================== ① 季度慢池（财报级，天级刷新）====================
    def get_pool(self) -> list:
        """对应 app.py 的 make_mock_pool()"""
        if not self.use_real:
            return self._mock_pool   # MOCK：直接用内置池

        # ---- 真实：沪深主板 + 流通市值>100亿 + 财报慢变量 ----
        try:
            # 1) 全市场基础信息（含申万行业）
            stock_info = ak.stock_info_a_code_name()
            # 过滤沪深主板（排除 688/300/8/4/9 开头）
            codes = [c for c in stock_info["code"].tolist()
                     if c.startswith(("60", "000", "001", "002"))]
            # 2) tushare 财报慢变量（一次性，开盘前拉取）
            basic = self._ts_daily_basic(codes)
            pool = []
            for code in codes[:500]:  # 首次先取前500只验证，跑通后可取消限制
                row = self._build_pool_row(code, basic)
                if row and row.get("circ_mv", 0) >= 100:  # 流通市值>100亿
                    pool.append(row)
            print(f"[data_source] 真实慢池构建完成：{len(pool)} 只")
            return pool
        except Exception as e:
            print(f"[data_source] 构建真实慢池失败：{e}，降级 MOCK")
            return self._mock_pool

    def _ts_daily_basic(self, codes):
        """tushare daily_basic：PE-TTM/市值/利润同比/股息率 等"""
        if not self.token or not _HAS_TS:
            return pd.DataFrame()
        try:
            if self._ts_pro is None:
                self._ts_pro = ts.pro_api(self.token)
            trade_date = self._ts_pro.trade_cal(is_open=1)["cal_date"].max()
            ts_codes = [f"{c}.SH" if c.startswith("6") else f"{c}.SZ" for c in codes]
            df = self._ts_pro.daily_basic(
                ts_code=",".join(ts_codes[:300]),  # tushare 有单次数量限制
                trade_date=trade_date,
                fields="ts_code,pe_ttm,pb,total_mv,circ_mv,free_share,profit_yoy,roe,dividend_yield",
            )
            return df
        except Exception as e:
            print(f"[data_source] tushare 调用失败：{e}")
            return pd.DataFrame()

    def _build_pool_row(self, code, basic_df) -> dict:
        """用 akshare 行业 + tushare 财务，组装成与 mock_pool 同结构的 dict"""
        try:
            sw_l1, sw_l2 = self._get_sw_industry(code)
            b = basic_df[basic_df["ts_code"].str.startswith(code)].iloc[0].to_dict() if not basic_df.empty else {}
            return {
                "code": code,
                "name": ak.stock_info_a_code_name().set_index("code").get(code, {}).get("name", code),
                "sw_l1": sw_l1, "sw_l2": sw_l2,
                "cycle": "weak",  # 周期强度由 cycle_filter.py 在慢池层统一打标
                "profit_yoy": b.get("profit_yoy", 0) or 0,
                "rev_yoy": 0, "roe": b.get("roe", 0) or 0,
                "gross_margin": 0, "debt_ratio": 0,
                "div_yield": (b.get("dividend_yield", 0) or 0) / 100,
                "total_mv": (b.get("total_mv", 0) or 0) / 10000,   # 万元→亿元
                "circ_mv": (b.get("circ_mv", 0) or 0) / 10000,
                "free_circ_mv": ((b.get("free_share", 0) or 0) / 1e8) * 0,  # 需×现价，盘中算
                "pb": b.get("pb", 0) or 0,
                "pe_static": 0, "pe_ttm": b.get("pe_ttm", 0) or 0, "pe_dyn": 0,
                "base_price": 0, "base_amount": 0,
                "net_super": 0, "net_big": 0, "net_mid": 0, "net_small": 0,
                "net_main5": 0, "net_main10": 0, "net_main20": 0,
            }
        except Exception:
            return None

    def _get_sw_industry(self, code):
        """申万行业归属（akshare 有接口，失败则返回未知）"""
        try:
            df = ak.stock_board_industry_name_em()  # 或使用 stock_sector_spot
            # 简化：实际建议用 akshare.stock_individual_info_em 取行业后映射申万
            return ("未知", "未知")
        except Exception:
            return ("未知", "未知")

    # ==================== ② 每轮盘中快照（行情级，15~30s）====================
    def snapshot(self, pool: list = None) -> list:
        """对应 app.py 的 MarketSimulator.snapshot()"""
        self.tick += 1
        if not self.use_real or not _HAS_AK:
            return self._mock_snapshot(pool or self._mock_pool)

        try:
            spot = ak.stock_zh_a_spot_em()   # 全市场快照（约23字段）
            if spot is None or spot.empty:
                raise RuntimeError("akshare 返回空")
            rows = []
            for _, s in spot.iterrows():
                code = str(s.get("代码", "")).zfill(6)
                if not code.startswith(("60", "000", "001", "002")):
                    continue  # 只要沪深主板
                row = self._spot_to_row(s, code)
                rows.append(row)
            # 用真实盘口 + 慢池财报合并（慢变量在 get_pool 时已算好，这里只补盘口）
            rows = self._merge_pool_financial(rows, pool)
            rows = [self._compute_main_positions(r) for r in rows]
            self._last_spot = rows
            return rows
        except Exception as e:
            print(f"[data_source] 真实快照失败：{e}，降级 MOCK")
            return self._mock_snapshot(pool or self._mock_pool)

    def _spot_to_row(self, s, code) -> dict:
        """akshare 快照字段 → app.py 内部字段名映射"""
        price = float(s.get("最新价", 0) or 0)
        prev = float(s.get("昨收", 0) or 0)
        chg = (price / prev - 1) * 100 if prev else 0
        return {
            "code": code,
            "name": s.get("名称", ""),
            "price": round(price, 2),
            "chg_pct": round(chg, 2),
            "speed_3m": 0,  # 需分钟级数据，候选池补
            "main_flow": 0, "net_super": 0, "net_big": 0, "net_mid": 0, "net_small": 0,
            "ddx1": 0, "in_out_ratio": 0,
            "vol_ratio": float(s.get("量比", 0) or 0),
            "turn": float(s.get("换手率", 0) or 0),
            "amount": (float(s.get("成交额", 0) or 0) / 1e8),  # 元→亿元
            "chg5": 0, "ddx5": 0, "net_main5": 0,
            "chg10": 0, "ddx10": 0, "net_main10": 0,
            "chg20": 0, "ddx20": 0, "net_main20": 0,
            "chg60": 0, "chg_yy": 0,
            "total_mv": (float(s.get("总市值", 0) or 0) / 1e8),
            "circ_mv": (float(s.get("流通市值", 0) or 0) / 1e8),
            "pb": float(s.get("市净率", 0) or 0),
            "pe_static": 0, "pe_ttm": float(s.get("市盈率-动态", 0) or 0), "pe_dyn": 0,
            # 财务字段开盘前由慢池补，此处先占位
            "profit_yoy": 0, "rev_yoy": 0, "roe": 0, "gross_margin": 0,
            "debt_ratio": 0, "div_yield": 0, "sw_l1": "未知", "sw_l2": "未知", "cycle": "weak",
            "free_circ_mv": 0,
        }

    def _merge_pool_financial(self, rows, pool):
        """把慢池的财报字段（profit_yoy/roe/debt_ratio 等）合并到快照"""
        if not pool:
            return rows
        fin = {p["code"]: p for p in pool}
        for r in rows:
            f = fin.get(r["code"], {})
            for k in ["profit_yoy", "rev_yoy", "roe", "gross_margin", "debt_ratio",
                      "div_yield", "sw_l1", "sw_l2", "cycle", "pe_static", "pe_dyn",
                      "net_super", "net_big", "net_mid", "net_small",
                      "net_main5", "net_main10", "net_main20", "free_circ_mv"]:
                if f.get(k) is not None:
                    r[k] = f[k]
        return rows

    # ==================== ③ 主力增仓% 双口径（与 app.py 完全一致）====================
    def _compute_main_positions(self, row: dict) -> dict:
        """复用 app.py 的 compute_main_positions 逻辑，保证口径统一"""
        net1 = (row.get("net_super", 0) or 0) + (row.get("net_big", 0) or 0)
        net5 = row.get("net_main5", net1 * 3)
        net10 = row.get("net_main10", net1 * 6)
        net20 = row.get("net_main20", net1 * 10)
        free = row.get("free_circ_mv") or row.get("circ_mv") or 0
        amount = row.get("amount", 0) or 0
        for net, k_free, k_amt in [
            (net1, "main_pos1", "main_pos1_amt"),
            (net5, "main_pos5", "main_pos5_amt"),
            (net10, "main_pos10", "main_pos10_amt"),
            (net20, "main_pos20", "main_pos20_amt"),
        ]:
            row[k_free] = round(net / free * 100, 2) if free else None
            row[k_amt] = round(net / amount * 100, 2) if amount else None
        return row

    # ==================== Mock 降级（保证始终有数据）====================
    def _mock_snapshot(self, pool) -> list:
        """原封不动保留 app.py 的 MarketSimulator 逻辑"""
        progress = min(1.0, self.tick / 20.0)
        rows = []
        for s in pool:
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
        return [self._compute_main_positions(r) for r in rows]


# ==================== 独立测试 ====================
if __name__ == "__main__":
    ds = DataSource()
    print("=== 季度慢池测试 ===")
    pool = ds.get_pool()
    print(f"慢池数量: {len(pool)}")
    print("样例:", pool[0] if pool else "空")
    print("\n=== 盘中快照测试 ===")
    snap = ds.snapshot(pool)
    print(f"快照数量: {len(snap)}")
    if snap:
        print("首行:", snap[0])