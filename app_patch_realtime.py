# -*- coding: utf-8 -*-
"""
app.py 集成补丁：接入腾讯+AkShare 实时数据源 + 手动慢池(manual_pool.csv)
=================================================================
只改 2 处，其余（COLUMNS / fast_filter / 样式 / 日志）完全不动。

==== 改动①：顶部 import 区，在 `from data_source import DataSource` 下方加一行 ====
    from realtime_source import RealtimeDataSource   # ← 新增

==== 改动②：session_state 初始化，把 DataSource(...) 那段替换为下面 ====

    # ---- 数据源选择（环境变量控制，无需改代码）----
    # DATASOURCE = "realtime"  -> 腾讯+AkShare 实时（推荐，无需 token）
    # DATASOURCE = "tushare"   -> TuShare 真实（需 TUSHARE_TOKEN，有限流）
    # DATASOURCE = "mock"      -> 强制模拟（离线调试）
    # USE_MANUAL_POOL = "true" -> 慢池用 manual_pool.csv（通达信 132 只），否则全市场
    ds_mode = os.getenv("DATASOURCE", "realtime").lower()
    use_manual = os.getenv("USE_MANUAL_POOL", "true").lower() in ("1", "true", "yes")

    if "ds" not in st.session_state:
        if ds_mode == "tushare":
            # 沿用 data_source.py 的 TuShare 逻辑（含缓存/降级）
            st.session_state.ds = DataSource(pool=make_mock_pool(), use_real=True)
        elif ds_mode == "mock":
            st.session_state.ds = DataSource(pool=make_mock_pool(), use_real=False)
        else:
            # ★ 默认：腾讯+AkShare 实时，无需 token、基本无限流
            st.session_state.ds = RealtimeDataSource(
                pool=make_mock_pool(),
                manual_pool_path="manual_pool.csv",
                use_manual_pool=use_manual,
                enrich_finance=False,   # 慢池财务较满 5000+ 只，先关闭；True=逐只补 AkShare 财务
            )

    if "sim" not in st.session_state:
        st.session_state.sim = MarketSimulator(make_mock_pool())  # 兜底（一般不再使用）

==== 改动③（可选，推荐）：顶部状态栏的 c5.write 显示 source，把"MOCK 模拟"改成动态 ====

    把原来这行：
        f"涨停色=涨/红  ·  数据: MOCK 模拟")
    替换为：
        src = getattr(st.session_state.ds, "source", "MOCK")
        note = getattr(st.session_state.ds, "error", "")
        f"涨停色=涨/红  ·  数据: {src}" + (f"  ·  {note}" if note else ""))

==== 使用方式 ====
    # 默认即实时（无需任何 token）：
        streamlit run app.py

    # 指定数据源：
        set DATASOURCE=realtime   && streamlit run app.py   # 腾讯+AkShare
        set DATASOURCE=tushare    && streamlit run app.py   # TuShare(需token)
        set DATASOURCE=mock       && streamlit run app.py   # 纯模拟

    # 手动慢池开关：
        set USE_MANUAL_POOL=true  && streamlit run app.py   # 用 manual_pool.csv
        set USE_MANUAL_POOL=false && streamlit run app.py   # 腾讯全市场主板

==== manual_pool.csv 格式（通达信 132 只，UTF-8 编码，逗号分隔）====
    code,name,sw_l1,sw_l2,cycle,base_price,profit_yoy,roe,debt_ratio,div_yield
    600547,山东黄金,有色金属,贵金属,mid_weak,28.0,30,10,60,1.0
    000001,平安银行,银行,股份制银行,weak,12.5,8.5,12.3,92,3.2
    ... (你的 132 只)

    最简版（只填 code 也行，其余实时源自动补齐）：
    code
    600547
    000001
    ...
"""
import os


# ==================================================================
# 下面这段可直接复制到 app.py 的「会话状态」区执行（含 fallback 兼容）
# ==================================================================
def build_data_source(mode: str = None, use_manual: bool = True, mock_pool=None):
    """
    工厂函数：根据环境变量/参数构建数据源。
    返回对象必须有：source / error / get_pool() / snapshot(pool)
    """
    mode = mode or os.getenv("DATASOURCE", "realtime").lower()
    use_manual = use_manual if use_manual is not None \
        else os.getenv("USE_MANUAL_POOL", "true").lower() in ("1", "true", "yes")

    if mode == "tushare":
        from data_source import DataSource
        return DataSource(pool=mock_pool, use_real=True)
    if mode == "mock":
        from data_source import DataSource, MockDataSource
        return DataSource(pool=mock_pool, use_real=False)

    # default: realtime（腾讯 + AkShare，无需 token）
    try:
        from realtime_source import RealtimeDataSource
        return RealtimeDataSource(
            pool=mock_pool,
            manual_pool_path="manual_pool.csv",
            use_manual_pool=use_manual,
            enrich_finance=False,
        )
    except Exception as e:
        # 极端情况（realtime_source 导入失败）-> 回退 Mock
        from data_source import DataSource
        ds = DataSource(pool=mock_pool, use_real=False)
        ds.error = f"实时源加载失败，降级 Mock：{e}"
        return ds


if __name__ == "__main__":
    # 自测
    print("DATASOURCE env:", os.getenv("DATASOURCE", "realtime"))
    ds = build_data_source()
    print("构建成功 ->", type(ds).__name__, "| source =", getattr(ds, "source", "?"))
