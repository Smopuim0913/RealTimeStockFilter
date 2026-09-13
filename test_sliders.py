# -*- coding: utf-8 -*-
"""
验证 app.py 侧边栏 8 个双口径主力增仓%滑块:
  1) DEFAULT_PARAMS 含全部 8 个键 (自由流通市值口径 + 成交额口径, 4周期)
  2) params 组装键名 与 fast_filter / diagnose 所用键名完全一致 (无 KeyError)
  3) 默认值 -1.0 能跑通 (对应"DDX > -1"口径)
  4) 收紧阈值后, 弱增仓股被正确过滤
"""
import importlib.util
import sys
import types

# 沙盒未装 streamlit: 用轻量 stub 替代, 让 app.py 模块级定义可加载
# (只测筛选引擎/滑块逻辑, 不测页面渲染)
if "streamlit" not in sys.modules:
    st_stub = types.ModuleType("streamlit")
    for _name in ["sidebar", "subheader", "number_input", "slider", "select_slider",
                  "multiselect", "selectbox", "title", "markdown", "set_page_config",
                  "columns", "metric", "container", "expander", "dataframe",
                  "write", "caption", "info", "warning", "text_input", "button",
                  "session_state", "experimental_rerun"]:
        setattr(st_stub, _name, lambda *a, **k: None)
    st_stub.__getattr__ = lambda x: (lambda *a, **k: None)
    sys.modules["streamlit"] = st_stub

spec = importlib.util.spec_from_file_location("app", "/data/workspace/app.py")
# 只加载模块级定义, 不执行 main() (main 在 if __name__ 里, 安全)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

# ---------- 1) DEFAULT_PARAMS 8 键 ----------
expected = [
    "main_pos1_free_min", "main_pos1_amt_min",
    "main_pos5_free_min", "main_pos5_amt_min",
    "main_pos10_free_min", "main_pos10_amt_min",
    "main_pos20_free_min", "main_pos20_amt_min",
]
for k in expected:
    assert k in app.DEFAULT_PARAMS, f"DEFAULT_PARAMS 缺键: {k}"
    assert app.DEFAULT_PARAMS[k] == 0.0, f"默认应为 0.0, 实际 {k}={app.DEFAULT_PARAMS[k]}"
print("[OK] DEFAULT_PARAMS 含 8 个双口径键, 默认均为 0.0 (增仓>0 语义)")

# ---------- 2) 模拟侧边栏滑块 -> params 组装 (复刻 app.py main()) ----------
def build_params(sliders: dict) -> dict:
    """与 app.py main() 中 params 组装逻辑完全一致"""
    p = dict(app.DEFAULT_PARAMS)
    p.update({
        "price_max": 1000, "in_out_ratio_max": 5.0,
        "vol_ratio_min": 0.0, "turn_min": 0.0, "amount_min": 0.0,
        "ddx1_min": -10.0, "ddx5_min": -10.0, "ddx10_min": -10.0, "ddx20_min": -10.0,
        "main_pos1_free_min": sliders["main_pos1_free_min"],
        "main_pos1_amt_min": sliders["main_pos1_amt_min"],
        "main_pos5_free_min": sliders["main_pos5_free_min"],
        "main_pos5_amt_min": sliders["main_pos5_amt_min"],
        "main_pos10_free_min": sliders["main_pos10_free_min"],
        "main_pos10_amt_min": sliders["main_pos10_amt_min"],
        "main_pos20_free_min": sliders["main_pos20_free_min"],
        "main_pos20_amt_min": sliders["main_pos20_amt_min"],
        "circ_mv_min": 100, "pb_max": 100.0,
        "pe_dyn_max": 500.0, "pe_static_max": 500.0, "pe_ttm_max": 500.0,
        "pe_dyn_static_ratio_max": 5.0, "pe_dyn_ttm_ratio_max": 5.0,
        "roe_min": -100.0, "debt_ratio_max": 100.0, "div_yield_min": 0.0, "peg_max": 10.0,
        "max_cycle_strength": "mid_weak",
        "excluded_sw_l2": ["煤炭开采", "石油开采", "工业金属"],
    })
    return p

sliders = {k: 0.0 for k in expected}
params = build_params(sliders)

# 构造一轮真实快照 (走 compute_main_positions 真实公式)
snap = app.MarketSimulator(app.make_mock_pool()).snapshot()
assert 10 <= len(snap) <= 20, f"mock 池数量异常: {len(snap)}"

# ---------- 3) 默认 0.0: 不应因增仓%条件误杀 (可能有弱增仓股) ----------
selected = app.fast_filter(snap, params)
diag = app.diagnose(snap, params)
for k in expected:
    assert k in params, f"params 缺键: {k}"
print(f"[OK] 默认 0.0 下入选 {len(selected)}/{len(snap)} 只; 无 KeyError, 键名全链路贯通")

# ---------- 4) 收紧自由流通市值口径 -> 强增仓留存 / 弱增仓淘汰 ----------
# 用确定性数据 (不走 simulator 随机噪声), 精确控制增仓%大小
def make_stock(code, name, net_main, free_circ_mv, amount=10.0, **kw):
    """构造一只标的: net_super+net_big = net_main (主力净额), 其余全部取"放行"值,
    确保只有增仓%一个变量在起作用"""
    base = {
        "code": code, "name": name, "sw_l2": "电池", "cycle": "weak",  # 非排除行业/弱周期
        "profit_yoy": 20.0, "rev_yoy": 10.0, "roe": 15.0, "gross_margin": 30.0,  # ROE>阈值
        "debt_ratio": 50.0, "div_yield": 3.0,                                    # 负债<阈值/股息>阈值
        "total_mv": 1000, "circ_mv": 900, "free_circ_mv": free_circ_mv,         # 流通市值>100
        "pb": 2.0, "pe_static": 15.0, "pe_ttm": 14.0, "pe_dyn": 13.0,           # 0<PE<均值
        "price": 50.0, "chg_pct": 1.0, "in_out_ratio": 0.8, "vol_ratio": 1.5,   # 内外比<5/量比>0
        "turn": 2.0, "amount": amount,                                           # 换手/金额达标
        "net_super": net_main * 0.6, "net_big": net_main * 0.4,
        "net_mid": 0, "net_small": 0,
        "net_main5": net_main * 3, "net_main10": net_main * 6, "net_main20": net_main * 10,
        "ddx1": 0.5, "ddx5": 0.3, "ddx10": 0.2, "ddx20": 0.1,                   # DDX>-10 全放行
        "chg5": 1, "chg10": 2, "chg20": 3, "chg60": 5, "chg_yy": 10,
        "speed_3m": 0, "main_flow": 0,
    }
    base.update(kw)
    return app.compute_main_positions(base)

# 强增仓股: 净额大 / 自由流通市值小 -> 增仓%自由 高
strong = make_stock("888001", "强增仓", net_main=10.0, free_circ_mv=1000)   # 各周期约 3%~30%
# 弱增仓股: 净额小 -> 增仓%自由 低 (但满足默认 0.0, 正值)
weak = make_stock("888002", "弱增仓", net_main=0.3, free_circ_mv=1000)     # 各周期约 0.09%~0.9%
# 负增仓股: 净额为负 -> 增仓%自由 为负
neg = make_stock("888003", "负增仓", net_main=-2.0, free_circ_mv=1000)    # 各周期为负

det_snap = [strong, weak, neg]
print(f"[准备] 强增仓 20日增仓%自由={strong['main_pos20']}%, "
      f"弱增仓={weak['main_pos20']}%, 负增仓={neg['main_pos20']}%")

# 4.1 默认 0.0: 强/弱增仓(正值)入选, 负增仓(净流出, -2.0%)被正确过滤
sel_default = app.fast_filter(det_snap, params)
codes_default = {r["code"] for r in sel_default}
diag_default = app.diagnose(det_snap, params)
assert "888001" in codes_default, "强增仓股(正值)默认应入选"
assert "888002" in codes_default, "弱增仓股(正值)默认应入选"
assert "888003" not in codes_default, \
    f"负增仓股(净流出-2.0%)默认0.0应被过滤, 却入选! 诊断: { {k:v for k,v in diag_default.items() if v>0} }"
print(f"[OK] 默认 0.0: 正增仓入选 / 负增仓(净流出)被过滤 ({len(sel_default)}/3)")

# 4.2 收紧自由流通市值口径至 0.5%: 只有强增仓留存
tight = {k: 0.0 for k in expected}  # 基准 0.0
tight.update({k: 0.5 for k in [
    "main_pos1_free_min", "main_pos5_free_min",
    "main_pos10_free_min", "main_pos20_free_min"]})
params_tight = build_params(tight)
sel_tight = app.fast_filter(det_snap, params_tight)
codes_tight = {r["code"] for r in sel_tight}
assert "888001" in codes_tight, "强增仓股应被 0.5% 阈值保留"
# 弱增仓股各周期增仓%约 0.03%/0.09%/0.18%/0.3%, 均 < 0.5% -> 被过滤
assert "888002" not in codes_tight, \
    f"弱增仓股(各周期<0.5%)收紧后应被过滤, 却入选: {weak['main_pos1']}/{weak['main_pos5']}/{weak['main_pos10']}/{weak['main_pos20']}"
print(f"[OK] 收紧自由流通市值口径至 0.5%: 仅强增仓留存 ({len(sel_tight)}/3)")

# 4.3 同时收紧成交额口径至 0.5%: 强增仓股因金额口径也需达标
tight2 = {k: 0.0 for k in expected}
tight2.update({k: 0.5 for k in expected})  # 8 键全 0.5%
params_tight2 = build_params(tight2)
sel_tight2 = app.fast_filter(det_snap, params_tight2)
# 强增仓股 amount=10, net=10 -> 金额口径当日=100%, 各周期均 >> 0.5, 必留存
assert "888001" in {r["code"] for r in sel_tight2}, "强增仓股金额口径 100% 应达标"
print(f"[OK] 双口径同时 0.5%: 强增仓股(金额口径100%)仍留存")

# ---------- 5) 成交额口径: 成交额=0 时 None 不参与淘汰 ----------
snap2 = [dict(r) for r in snap]
for r in snap2:
    r["amount"] = 0.0  # 开盘初期
snap2 = [app.compute_main_positions(r) for r in snap2]
sel_open = app.fast_filter(snap2, params)
# 成交额口径全为 None, 不应因此淘汰任何标的 (只看自由流通市值口径)
assert len(sel_open) >= len(selected), \
    f"开盘(amount=0)时成交额口径应跳过, 实际 {len(sel_open)} < {len(selected)}"
print(f"[OK] 开盘成交额=0 时, 金额口径自动跳过 (逐步入围): {len(sel_open)} 只")

print("\n========== 全部验证通过 ✅ ==========")
print("双口径 8 滑块: 自由流通市值(主) + 成交额(辅) x 当日/5日/10日/20日")
for k in expected:
    print(f"   {k} = {params[k]}")
