## 数据源与缓存机制

`data_source.py` 是可插拔数据源：**TuShare 真实数据** / **内置 Mock 模拟**，自动降级。

### 一、自动切换逻辑

```
有 TUSHARE_TOKEN 且 tushare 可用  →  真实数据（右上角显示 "Tushare 真实"）
否则                              →  Mock 模拟（右上角显示降级原因）
```

初始化（app.py）：
```python
from data_source import DataSource
st.session_state.ds = DataSource(pool=make_mock_pool(), use_real=None)
# use_real=None 自动判断；True 强制真实；False 强制 Mock
```

### 二、配置步骤（只需一次）

1. 注册 TuShare Pro 获取免费 token：https://tushare.pro/register
2. 复制配置模板，填入你的 token：
   ```bash
   cp .env.example .env
   # 编辑 .env，把 TUSHARE_TOKEN= 后面填上你的 token
   ```
3. 安装依赖：
   ```bash
   pip install -r requirements.txt   # 含 python-dotenv
   ```
4. 启动：
   ```bash
   streamlit run app.py
   ```

### 三、为什么有缓存（重要）

**TuShare 免费积分对 `stock_basic` / `trade_cal` 等接口限制 1次/小时**。为避免反复触发限流：

| 数据 | 缓存时长 | 说明 |
|------|---------|------|
| 慢池（pool） | **12 小时** | 财报+估值+市值，日级变化 |
| 快照（snapshot） | **5 分钟** | 盘中行情，盘中级刷新 |

- 缓存目录：项目根 `.cache/`（已在 `.gitignore`）
- **限流期间自动用【过期缓存】兜底**，保证界面不断流
- 缓存过期后首次请求会重取；取不到仍返回过期数据

### 四、免费积分能拿到什么（实测）

你的项目用到的接口与积分门槛：

| 接口 | 用途 | 免费积分 |
|------|------|---------|
| `stock_basic` | 股票列表/行业 | ✅ 可用（1次/小时） |
| `trade_cal` | 交易日历 | ✅ 可用（1次/小时） |
| `daily_basic` | PE/PB/市值/换手/量比 | ✅ 可用 |
| `moneyflow` | 大单/超大单净额、内外比近似 | ⚠️ 部分需积分 |
| `fina_indicator` | ROE/利润同比/毛利率/负债率 | ❌ 需较高积分（降级为 0 占位） |

**降级策略**：`fina_indicator` 无权限时，财务字段（profit_yoy/roe 等）用 0 占位，**不阻断主流程**，界面仍可跑（这些字段在筛选中默认阈值较宽松）。

### 五、诊断真实数据源

```bash
python test_ts.py
```

逐接口测试 token 权限，输出形如：
```
[1] stock_basic: OK (5000+ rows)
[2] trade_cal: OK
[3] daily_basic: OK
[4] moneyflow: 空（降级）
[5] fina_indicator: 异常（降级）
```

### 六、界面右上角状态说明

| 显示 | 含义 |
|------|------|
| `数据: Tushare 真实` | 真实数据，慢池+快照均来自 TuShare |
| `数据: MOCK 模拟 · 降级原因: ...` | 降级原因直接可见，按提示处理 |

常见降级原因：
- `未设置 TUSHARE_TOKEN` → 填 `.env`
- `stock_basic 返回 0 行（token 积分/权限不足）` → 攒积分或等限流窗口（1小时）
- `fina_indicator 降级（...）` → 正常，财务字段占位

### 七、目录结构（数据源相关）

```
RealTimeStockFilter/
├── app.py                  # 界面层（改动见 app_patch.py）
├── data_source.py          # ★ 可插拔数据源（真实/Mock/缓存）
├── cache.py                # 本地 TTL 缓存
├── test_data_source.py     # 单元测试（双口径公式/防除零/接口）
├── test_app_integration.py # app.py 集成链路测试
├── test_ts.py              # TuShare 接口权限诊断
├── .env.example             # 配置模板（不含真实 token）
├── .cache/                 # 本地缓存（git 忽略）
└── requirements.txt
```
