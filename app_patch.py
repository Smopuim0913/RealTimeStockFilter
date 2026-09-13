# -*- coding: utf-8 -*-
"""
============================================================
app.py 改动补丁（共 2 处，对齐新版 data_source.py）
============================================================

【改动 1】session_state 初始化
  位置：搜索 `if "ds" not in st.session_state:`
  把整段替换成下面这段（只加了一行 mock_pool_fn，其余不变）

------------------------------------------------------------
if "ds" not in st.session_state:
    # use_real=None ：有 TUSHARE_TOKEN 且 tushare 可用就走真实，否则 Mock
    st.session_state.ds = DataSource(
        pool=make_mock_pool(),
        use_real=None,
        mock_pool_fn=make_mock_pool,   # ← 新增：实盘失败时用这个生成 Mock 兜底
    )
if "sim" not in st.session_state:
    st.session_state.sim = MarketSimulator(make_mock_pool())
------------------------------------------------------------

【改动 2】顶部状态栏取数逻辑
  位置：搜索 `pool_size = len(pool)` 或 `c5.write(...)`
  把「with header:」里面、从"先取数"到"c5.write(...)"整段替换成下面这段

  关键顺序：先定义 ds/pool/snapshot，再做 metric 展示
  这样无论真实数据是否成功，pool 都一定有值（不再 UnboundLocalError）

------------------------------------------------------------
        # ====== ① 先取数（pool 必须先赋值，才能展示/筛选）======
        ds = st.session_state.ds
        pool = make_mock_pool()          # 兜底默认值，保证 len(pool) 不报错
        snapshot = None

        try:
            real_pool = ds.get_pool()   # ① 季度慢池（真实 or Mock）
            if real_pool:
                pool = real_pool
            snapshot = ds.snapshot(pool)  # ② 盘中快照（真实 or None）
        except Exception as e:
            print(f"[app] 真实数据源异常：{e}")

        if not snapshot:                 # 兜底：走 Mock 快照
            snapshot = st.session_state.sim.snapshot()

        # ====== ② 再展示（pool/snapshot 此刻一定已就绪）======
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 2])
        c1.metric("选中条件", f"{len(DEFAULT_ORDER)} 字段")
        pool_size = len(pool)            # ✅ pool 之前已赋值
        c2.metric("季度慢池", pool_size)
        selected = fast_filter(snapshot, params)
        prev_map = st.session_state.prev
        curr_codes = {r["code"] for r in selected}
        prev_codes = set(prev_map.keys())
        entered = curr_codes - prev_codes
        exited = prev_codes - curr_codes
        c3.metric("当前入选", len(selected), delta=f"+{len(entered)}")
        c4.metric("本轮回局", len(exited), delta=f"-{len(exited)}" if exited else None)

        # ====== ③ 右上角数据来源标签（真实/降级原因可见）======
        src = getattr(ds, "source", "Mock")
        err = getattr(ds, "error", "")
        label = "Tushare 真实" if src == "Tushare" else "MOCK 模拟"
        c5.write(
            f"**最后更新**: {datetime.now().strftime('%H:%M:%S')}  ·  "
            f"下一轮 {refresh_rate}s  ·  数据: {label}"
            + (f"  ·  降级原因: {err}" if err else "")
        )
------------------------------------------------------------

   ⚠️ 注意：替换后全文只剩「一处」 `pool_size = len(pool)`（删掉原来的那行）

【改动 3（可选，推荐）】依赖文件
  项目根新建 requirements.txt（内容见下方），把 python-dotenv 补进去：

    streamlit>=1.30
    pandas>=2.0
    numpy>=1.24
    akshare>=1.13.0
    tushare>=1.2.89
    requests>=2.28.0
    lxml>=4.9
    beautifulsoup4>=4.11
    python-dotenv>=1.0

============================================================
本地验证顺序（在 L:\\Stock\\RealTimeStockFilter 下）：
  1) pip install python-dotenv
  2) 确认 .env 里有 TUSHARE_TOKEN=你的token
  3) python test_ts.py        <- 先看各接口是否返回数据、有无积分不足
  4) streamlit run app.py     <- 右上角应显示「Tushare 真实」或降级原因
============================================================
"""
