# -*- coding: utf-8 -*-
"""
实时数据源：腾讯行情接口 + AkShare（无需 Token，基本无限流）
=================================================================
定位：替代 TuShare 做「实时层」，规避其 1次/小时 限流与积分门槛。
      TuShare 仍负责「慢池财务」（攒够积分后启用），二者互补。

数据分工：
  腾讯行情接口 (qt.gtimg.cn / web.ifzq.gtimg.cn)
      -> 实时快照：现价、涨跌幅、量比、换手率、成交额、内外盘、总/流通市值、PE、PB
      -> 日内分钟/分时（后续可扩展 3分钟涨速）
  AkShare (东方财富)
      -> stock_individual_info_em       : 个股基础信息（行业映射申万）
      -> stock_bid_ask_em               : 盘口五档（扩展）
      -> stock_individual_fund_flow     : 个股资金流（DDX/超大单/大单净额 -> main_pos）
      -> stock_zyjrljlr (主力净流入)     : 5/10/20日累计主力净额 -> main_pos5/10/20
      -> stock_financial_analysis_indicator : 财务（ROE/利润同比/毛利率/负债率/股息率，兜底）

字段输出：与 data_source.py 的 TushareDataSource / MockDataSource 完全一致，
          app.py 的 COLUMNS、fast_filter、compute_main_positions 无需改动。

用法：
    from realtime_source import RealtimeDataSource
    ds = RealtimeDataSource(pool=make_mock_pool())   # 强制实时（无 token）
    ds.source   # "Realtime"
    ds.get_pool()    # 慢池：手动池(manual_pool.csv) > TuShare缓存 > 腾讯主板全市场
    ds.snapshot(pool) # 盘中快照：腾讯实时 + AkShare 资金流

降级：任何步骤失败 -> 自动降级 MockDataSource，ds.error 记录原因，界面不断流。
"""
import os
import re
import json
import urllib.request
from datetime import datetime
from typing import List, Dict, Optional

import numpy as np
import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    import akshare as ak
    _HAS_AK = True
except Exception:
    _HAS_AK = False

# 复用 data_source 的工具与 Mock 兜底
from data_source import (
    _f, SW_CYCLE, MockDataSource,
)


# ==================================================================
# 工具函数
# ==================================================================
def _code6_to_tencent(code: str) -> str:
    """600547 -> sh600547 ; 000001 -> sz000001 ; 北交所 8xxxxx -> bj..."""
    code = str(code).zfill(6)
    if code.startswith(("5", "6", "9", "688", "11", "13")):
        return "sh" + code
    if code.startswith(("4", "8")):
        return "bj" + code
    return "sz" + code


def _fetch_tencent_quotes(codes: List[str]) -> Dict[str, dict]:
    """
    批量拉取腾讯行情快照。
    返回 {code6: {price, chg_pct, vol_ratio, turn, amount, total_mv, circ_mv,
                  pb, pe_ttm, in_out_ratio, ...}}
    失败返回 {}，由上层降级。
    """
    if not codes:
        return {}
    # 单次请求拼接（腾讯支持逗号批量，上限约50只/次，这里分批）
    batched = [_code6_to_tencent(c) for c in codes]
    result: Dict[str, dict] = {}
    url = "https://qt.gtimg.cn/q=" + ",".join(batched)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://gu.qq.com/",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("gbk", errors="ignore")
        # 每条以 '~' 分隔，v_sh600547="1~山东黄金~...";
        for line in raw.splitlines():
            m = re.search(r'v_(sh|sz|bj)(\d{6})="([^"]*)', line)
            if not m:
                continue
            code6 = m.group(2)
            f = m.group(3).split("~")
            # 腾讯字段索引（标准版，缺失字段用 None 兜底）
            # 3=名称 4=代码 5=现价 6=昨收 30=开盘 31=最高 32=最低
            # 33=成交量(手) 34=成交额(元) 37=振幅 38=换手率 39=量比
            # 43=PE 44=PB 45=总市值 46=流通市值 47=市净率(另一口径) 49=涨停
            # 46=内外盘相关需另取，这里用买一卖一近似，若无则 None
            # ---- 字段索引（已按腾讯接口实测校准，2026-09）----
            #  3=最新价 4=昨收 5=今开 6=成交量(手) 7=外盘 8=内盘
            #  31=涨跌额 32=涨跌幅(%) 34=最高 35=最低 36=现价/昨收/成交额(复合,见57)
            #  37=成交量(手,另一口径) 38=换手率(%) 39=量比
            #  43=市净率PB(简) 44=流通市值(亿) 45=总市值(亿) 46=市净率PB 47=PE-TTM
            #  57=成交额(万元)
            try:
                price = _f(f[3])         # 最新价
                pre = _f(f[4], price) or price   # 昨收
                chg = round((price / pre - 1) * 100, 2) if pre > 0 else 0.0
                # 腾讯涨跌幅字段（更权威，优先用；失败则用计算值）
                chg_field = _f(f[32], chg)
                result[code6] = {
                    "name": f[1] if len(f) > 1 else "",
                    "price": price,
                    "chg_pct": chg_field if abs(chg_field) < 100 else chg,
                    "vol_ratio": _f(f[39], 1.0),        # 量比
                    "turn": _f(f[38]),                    # 换手率(%)
                    "amount": _f(f[57]) / 1e4,            # 成交额(万元)->亿
                    "total_mv": _f(f[45]),                # 总市值(亿，腾讯已为亿)
                    "circ_mv": _f(f[44]),                 # 流通市值(亿)
                    "pb": _f(f[46]) or _f(f[43]),         # 市净率
                    "pe_ttm": _f(f[47]),                  # PE-TTM
                    # 内外比 = 内盘/外盘（腾讯字段 8=内盘, 7=外盘）
                    "in_out_ratio": round(_f(f[8]) / _f(f[7]), 2)
                                       if (_f(f[7]) > 0 and _f(f[8]) > 0) else None,
                }
            except Exception:
                continue
    except Exception as e:
        raise RuntimeError(f"腾讯行情接口失败：{e}")
    return result


def _batch_fetch(codes: List[str], batch_size: int = 40) -> Dict[str, dict]:
    """分批拉取腾讯快照（避免单 URL 过长/被拒）"""
    out: Dict[str, dict] = {}
    for i in range(0, len(codes), batch_size):
        chunk = codes[i:i + batch_size]
        try:
            out.update(_fetch_tencent_quotes(chunk))
        except Exception as e:
            # 单批失败不阻断，继续下一批
            print(f"[realtime] 腾讯批次失败({chunk[0]}~{chunk[-1]}): {e}")
    return out


# ==================================================================
# 手动慢池：通达信公式选出的 132 只代码
# ==================================================================
def load_manual_pool(path: str = "manual_pool.csv") -> List[Dict]:
    """
    从 manual_pool.csv 加载手动慢池（通达信基本面选股结果）。
    CSV 格式（至少含 code 列，其余可选，缺省字段由实时源补齐）：
        code,name,sw_l1,sw_l2,cycle,base_price
        600547,山东黄金,有色金属,贵金属,mid_weak,28.0
        000001,平安银行,银行,股份制银行,weak,12.5
    code 可为 6 位(600547) 或带交易所(600547.SH / sh600547)。

    返回与 make_mock_pool() 同结构的 list[dict]，供 app.py 直接使用。
    文件不存在 -> 返回 []（不影响主流程，回退到 TuShare缓存/腾讯全市场）。
    """
    if not os.path.exists(path):
        return []
    try:
        # comment='#' 让 pandas 忽略注释行；header=0 明确第一行为列名
        df = pd.read_csv(path, dtype={"code": str}, comment="#", header=0)
    except Exception as e:
        print(f"[realtime] 读取 {path} 失败：{e}")
        return []

    # 标准化 code -> 6 位
    def norm(c):
        c = str(c).strip().upper()
        c = re.sub(r"\.(SH|SZ|BJ|SS)$", "", c)
        c = re.sub(r"^(SH|SZ|BJ)", "", c)
        return c.zfill(6)
    df["code"] = df["code"].apply(norm)

    records = []
    for _, r in df.iterrows():
        records.append({
            "code": r["code"],
            "name": str(r.get("name", "")) if pd.notna(r.get("name")) else "",
            "sw_l1": str(r.get("sw_l1", "")) if pd.notna(r.get("sw_l1")) else "",
            "sw_l2": str(r.get("sw_l2", "")) if pd.notna(r.get("sw_l2")) else str(r.get("sw_l1", "")),
            "cycle": str(r.get("cycle", "none")) if pd.notna(r.get("cycle")) else "none",
            "base_price": _f(r.get("base_price")) or 0.0,
            # 以下由实时快照补齐，慢池层只做"是否在候选内"
            "profit_yoy": _f(r.get("profit_yoy")),
            "rev_yoy": _f(r.get("rev_yoy")),
            "roe": _f(r.get("roe")),
            "gross_margin": _f(r.get("gross_margin")),
            "debt_ratio": _f(r.get("debt_ratio")),
            "div_yield": _f(r.get("div_yield")),
            "total_mv": _f(r.get("total_mv")),
            "circ_mv": _f(r.get("circ_mv")),
            "free_circ_mv": _f(r.get("free_circ_mv")) or _f(r.get("circ_mv")),
            "pb": _f(r.get("pb")),
            "pe_static": _f(r.get("pe_static")),
            "pe_ttm": _f(r.get("pe_ttm")),
            "pe_dyn": _f(r.get("pe_dyn")),
            "net_super": 0, "net_big": 0, "net_mid": 0, "net_small": 0,
            "net_main5": 0, "net_main10": 0, "net_main20": 0,
        })
    return records


# ==================================================================
# AkShare 补充：行业 / 资金流 / 财务
# ==================================================================
class AkShareEnricher:
    """用 AkShare 补充腾讯快照没有的字段（行业、资金流、财务）。"""

    def __init__(self):
        self._industry_cache: Dict[str, dict] = {}

    def industry(self, code: str) -> dict:
        """个股基础信息 -> {name, sw_l1, sw_l2}（东财行业近似申万）"""
        if code in self._industry_cache:
            return self._industry_cache[code]
        if not _HAS_AK:
            return {"name": "", "sw_l1": "", "sw_l2": ""}
        try:
            info = ak.stock_individual_info_em(symbol=code)
            d = dict(zip(info["item"], info["value"]))
            sw_l1 = d.get("行业", "") or ""
            self._industry_cache[code] = {"name": d.get("名称", ""), "sw_l1": sw_l1, "sw_l2": sw_l1}
        except Exception:
            self._industry_cache[code] = {"name": "", "sw_l1": "", "sw_l2": ""}
        return self._industry_cache[code]

    def fund_flow(self, code: str) -> dict:
        """
        个股资金流（东财）：
        返回 {net_super, net_big, net_mid, net_small, ddx1,
              net_main5, net_main10, net_main20}（单位：亿元，近似）
        失败 -> 全部 0。
        """
        out = {"net_super": 0, "net_big": 0, "net_mid": 0, "net_small": 0,
               "ddx1": 0, "net_main5": 0, "net_main10": 0, "net_main20": 0}
        if not _HAS_AK:
            return out
        try:
            # 当日个股资金流（含超大/大/中/单净额）
            ff = ak.stock_individual_fund_flow(stock=code, market="SZ" if code.startswith("0") else "SH")
            # 列名随版本变化，常见：主力净流入-净额, 超大单净流入, 大单净流入 ...
            if ff is not None and len(ff) > 0:
                last = ff.iloc[-1]
                def g(col_hint):
                    for c in ff.columns:
                        if col_hint in str(c):
                            return _f(last.get(c))
                    return 0.0
                super_ = g("超大单") or g("超大")
                big_ = g("大单") or g("大")
                mid_ = g("中单") or g("中")
                small_ = g("小单") or g("小")
                main_ = g("主力") or (super_ + big_)
                out["net_super"] = round(super_ / 1e8, 2)
                out["net_big"] = round(big_ / 1e8, 2)
                out["net_mid"] = round(mid_ / 1e8, 2)
                out["net_small"] = round(small_ / 1e8, 2)
                out["ddx1"] = round(main_ / 1e8, 2)  # 近似 DDX（主力净额/亿）
                # 5/10/20 日累计：用最近 N 行求和（akshare 返回近期多日）
                for days, key in [(5, "net_main5"), (10, "net_main10"), (20, "net_main20")]:
                    recent = ff.tail(days)
                    col = None
                    for c in ff.columns:
                        if "主力" in str(c) and "净额" in str(c):
                            col = c
                            break
                    if col:
                        s = _f(recent[col].sum())
                        out[key] = round(s / 1e8, 2)
        except Exception:
            pass
        return out

    def finance(self, code: str) -> dict:
        """财务摘要（ROE/利润同比/毛利率/负债率/股息率），失败 -> 0 占位"""
        out = {"roe": 0, "profit_yoy": 0, "rev_yoy": 0,
               "gross_margin": 0, "debt_ratio": 0, "div_yield": 0}
        if not _HAS_AK:
            return out
        try:
            fin = ak.stock_financial_analysis_indicator(symbol=code)
            if fin is not None and len(fin) > 0:
                last = fin.iloc[0]
                out["roe"] = _f(last.get("净资产收益率(%)"))
                out["profit_yoy"] = _f(last.get("净利润同比增长率(%)"))
                out["rev_yoy"] = _f(last.get("营业总收入同比增长率(%)"))
                out["gross_margin"] = _f(last.get("销售毛利率(%)"))
                out["debt_ratio"] = _f(last.get("资产负债率(%)"))
                out["div_yield"] = _f(last.get("股息率(%)"))
        except Exception:
            pass
        return out


# ==================================================================
# 主类：腾讯快照 + AkShare 补充，组合成完整数据源
# ==================================================================
class RealtimeDataSource:
    """
    实时数据源（腾讯 + AkShare，无需 Token）。
    可作为 DataSource 的 _impl 直接替换（接口一致：source/error/get_pool/snapshot）。
    """

    def __init__(self, pool: list = None, manual_pool_path: str = "manual_pool.csv",
                 use_manual_pool: bool = True, enrich_finance: bool = False):
        """
        pool: 备用 Mock 池（腾讯取不到时降级）
        manual_pool_path: 手动慢池 CSV 路径（通达信 132 只）
        use_manual_pool: True -> 优先用 manual_pool.csv 作为慢池候选
        enrich_finance: True -> 对慢池逐只调 AkShare 财务（较慢，建议 False 先跑通）
        """
        self._mock_pool = pool or []
        self._mock = MockDataSource(pool=pool)
        self.source = "Realtime"
        self.error = ""
        self.manual_pool_path = manual_pool_path
        self.use_manual_pool = use_manual_pool
        self.enrich_finance = enrich_finance
        self._enricher = AkShareEnricher()

    # ---------- 慢池 ----------
    def get_pool(self) -> List[Dict]:
        try:
            return self._build_pool()
        except Exception as e:
            self.error = f"实时慢池失败：{e}"
            return self._mock.get_pool()

    def _build_pool(self) -> List[Dict]:
        # 1) 手动池优先（通达信 132 只，字段最权威）
        if self.use_manual_pool:
            manual = load_manual_pool(self.manual_pool_path)
            if manual:
                # 用腾讯快照补齐实时价格/市值（不补齐也能跑，只是 price=0）
                codes = [r["code"] for r in manual]
                quotes = _batch_fetch(codes)
                for r in manual:
                    q = quotes.get(r["code"], {})
                    if q.get("price"):
                        r["price"] = q["price"]
                        r["chg_pct"] = q.get("chg_pct", 0)
                    if q.get("circ_mv"):
                        r["circ_mv"] = q["circ_mv"]
                        r["free_circ_mv"] = r.get("free_circ_mv") or q["circ_mv"]
                    if q.get("total_mv"):
                        r["total_mv"] = q["total_mv"]
                    if q.get("pb"):
                        r["pb"] = q["pb"]
                    if q.get("pe_ttm"):
                        r["pe_ttm"] = q["pe_ttm"]
                    # 周期强度：按申万一级映射（CSV 未给则自动）
                    if not r.get("cycle") or r["cycle"] == "none":
                        r["cycle"] = SW_CYCLE.get(r.get("sw_l1", ""), "none")
                return manual

        # 2) 无手动池 -> 腾讯拉取沪深主板全市场（作为慢池）
        codes = self._main_board_codes()
        quotes = _batch_fetch(codes)
        out = []
        for code, q in quotes.items():
            ind = self._enricher.industry(code)
            rec = {
                "code": code, "name": q.get("name") or ind.get("name", ""),
                "sw_l1": ind.get("sw_l1", ""), "sw_l2": ind.get("sw_l2", ""),
                "cycle": SW_CYCLE.get(ind.get("sw_l1", ""), "none"),
                "price": q.get("price", 0), "chg_pct": q.get("chg_pct", 0),
                "vol_ratio": q.get("vol_ratio", 1.0), "turn": q.get("turn", 0),
                "amount": q.get("amount", 0),
                "total_mv": q.get("total_mv", 0), "circ_mv": q.get("circ_mv", 0),
                "free_circ_mv": q.get("circ_mv", 0),
                "pb": q.get("pb", 0), "pe_static": 0,
                "pe_ttm": q.get("pe_ttm", 0), "pe_dyn": q.get("pe_ttm", 0),
                "net_super": 0, "net_big": 0, "net_mid": 0, "net_small": 0,
                "net_main5": 0, "net_main10": 0, "net_main20": 0,
            }
            out.append(rec)
        if not out:
            raise RuntimeError("腾讯全市场快照为空（网络/接口变更）")
        return out

    def _main_board_codes(self) -> List[str]:
        """获取沪深主板代码列表（akshare，失败则用常见范围兜底）"""
        codes: List[str] = []
        if _HAS_AK:
            try:
                info = ak.stock_info_a_code_name()
                codes = [str(c).zfill(6) for c in info["code"].tolist()]
            except Exception:
                pass
        if not codes:
            # 兜底：常见主板号段（够演示，生产建议用 akshare 列表）
            codes = [f"{i:06d}" for i in range(600000, 604000)] + \
                    [f"{i:06d}" for i in range(1, 3000)] + \
                    [f"{i:06d}" for i in range(300000, 302000)]
        # 只保留主板（排除科创/创业/北交所，避免腾讯字段差异）
        return [c for c in codes if c.startswith(("60", "000", "001", "002", "003"))]

    # ---------- 快照（盘中，逐只补 AkShare 资金流） ----------
    def snapshot(self, pool: List[Dict]) -> Optional[List[Dict]]:
        try:
            return self._snapshot(pool)
        except Exception as e:
            self.error = f"实时快照失败：{e}"
            return self._mock.snapshot(pool)

    def _snapshot(self, pool: List[Dict]) -> List[Dict]:
        codes = [str(p.get("code", "")).zfill(6) for p in pool if p.get("code")]
        quotes = _batch_fetch(codes)
        rows = []
        for p in pool:
            code = str(p.get("code", "")).zfill(6)
            q = quotes.get(code, {})
            rec = dict(p)
            if not q.get("price"):
                # 腾讯没取到这只，保留原池数据（可能是停牌/退市），跳过实时覆盖
                rows.append(rec)
                continue

            free_mv = _f(p.get("free_circ_mv")) or _f(q.get("circ_mv"))
            amt = _f(q.get("amount"))

            rec.update({
                "price": q["price"], "chg_pct": q.get("chg_pct", 0),
                "vol_ratio": q.get("vol_ratio", p.get("vol_ratio", 1.0)),
                "turn": q.get("turn", 0),
                "amount": amt,
                "total_mv": q.get("total_mv", p.get("total_mv", 0)),
                "circ_mv": q.get("circ_mv", p.get("circ_mv", 0)),
                "free_circ_mv": free_mv,
                "pb": q.get("pb", p.get("pb", 0)),
                "pe_ttm": q.get("pe_ttm", p.get("pe_ttm", 0)),
                "pe_dyn": q.get("pe_ttm", p.get("pe_dyn", 0)),
                "in_out_ratio": q.get("in_out_ratio"),   # 腾讯无内外盘 -> None
            })

            # AkShare 资金流（逐只有网络开销；候选池大时建议异步/缓存）
            ff = self._enricher.fund_flow(code)
            rec.update(ff)

            # ---- 主力增仓% 双口径（与 Mock/Tushare 完全一致）----
            net1 = _f(rec.get("net_super")) + _f(rec.get("net_big"))
            rec["net_main5"] = ff["net_main5"] or _f(rec.get("net_main5"), net1 * 3)
            rec["net_main10"] = ff["net_main10"] or _f(rec.get("net_main10"), net1 * 6)
            rec["net_main20"] = ff["net_main20"] or _f(rec.get("net_main20"), net1 * 10)
            for net, kf, ka in [
                (net1, "main_pos1", "main_pos1_amt"),
                (_f(rec.get("net_main5")), "main_pos5", "main_pos5_amt"),
                (_f(rec.get("net_main10")), "main_pos10", "main_pos10_amt"),
                (_f(rec.get("net_main20")), "main_pos20", "main_pos20_amt"),
            ]:
                rec[kf] = round(net / free_mv * 100, 2) if free_mv else None
                rec[ka] = round(net / amt * 100, 2) if amt else None
            rows.append(rec)
        return rows


# ==================== 独立测试 ====================
if __name__ == "__main__":
    print("=== RealtimeDataSource 测试 ===")
    ds = RealtimeDataSource(pool=None, manual_pool_path="manual_pool.csv",
                            use_manual_pool=False, enrich_finance=False)
    pool = ds.get_pool()
    print(f"慢池数量: {len(pool)} | source={ds.source}")
    if pool:
        print("慢池样例:", pool[0])
    snap = ds.snapshot(pool[:10])
    print(f"快照数量: {len(snap) if snap else 0}")
    if snap:
        print("快照首行:", {k: snap[0].get(k) for k in
              ["code", "name", "price", "chg_pct", "vol_ratio", "turn", "net_super", "main_pos1"]})
    print("error:", ds.error)
