# 沪深京 A 股实时行情筛选器

> 九方智投 / 同花顺条件选股风格的 **A 股（沪深京）多条件实时筛选器**。
> 基于 `akshare` + `tushare` + 腾讯行情接口，采用 **季度慢池 + 盘中快筛 + diff 自动进出** 架构。
> 适合想自己跑条件选股、又不想装商业软件的个人投资者。

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](https://github.com/Smopuim0913/RealTimeStockFilter)

---

## 📖 目录

- [这是什么？](#-这是什么)
- [核心亮点](#-核心亮点)
- [筛选字段一览](#-筛选字段一览)
- [核心架构](#-核心架构)
- [快速开始（小白版）](#-快速开始小白版)
  - [方式一：本地 Python（推荐新手）](#方式一本地-python推荐新手)
  - [方式二：Docker 一键（跨平台，免配环境）](#方式二docker-一键跨平台免配环境)
  - [方式三：Streamlit Cloud（免安装，打开网页就用）](#方式三streamlit-cloud免安装打开网页就用)
- [配置说明（`.env`）](#-配置说明env)
- [使用说明](#-使用说明)
- [数据来源与字段实现状态](#-数据来源与字段实现状态)
- [文件结构](#-文件结构)
- [常见问题（FAQ）](#-常见问题faq)
- [路线图（Roadmap）](#-路线图roadmap)
- [如何参与贡献（求大佬 PR）](#-如何参与贡献求大佬-pr)
- [免责声明](#-免责声明)

---

## 🤔 这是什么？

一个运行在你自己电脑（或云服务器）上的 **A 股条件选股工具**：

- 你设定一组筛选条件（例如：沪深主板 + 流通市值 > 100 亿 + 动态 PE < 市场均值 + 当日主力增仓% > 0 + 内外比 < 0.8 + 量比 > 1.5 …）；
- 程序**每隔十几秒**拉取一次实时行情，自动筛出当前满足条件的股票；
- 行情波动导致某只股票**新满足条件 → 标记为「✅ 进入」**；**不再满足 → 标记为「❌ 出局」**；
- 界面是网页表格（Streamlit），**一屏显示 40+ 字段**，支持拖动排序列、调整列宽、进入/出局高亮。

> 💡 你可以把它理解为：**把九方智投 / 同花顺的「条件选股」搬到你自己可控的开源工具里**，数据用公开行情接口，不依赖商业软件。

![界面示意（待补充截图）](#)

---

## ✨ 核心亮点

| 特性 | 说明 |
|---|---|
| 🎯 **40+ 筛选字段** | 行情 / 资金 / DDX / 盘口 / 阶段涨幅 / 估值 / 财务全覆盖 |
| 🔄 **自动进入 / 出局** | 两轮结果做集合差，行情波动实时反映 |
| 📊 **主力增仓% 双口径** | 自由流通市值口径（主，跨市值可比）+ 成交额口径（辅，主力参与度），当日/5/10/20 日各两列共 8 列 |
| 🏭 **周期股过滤** | 申万行业分级（强/中强/中/中弱/弱/无）+ 强度滑块 + 申万二级精细排除 + 周期性评分模型 |
| 🧠 **季度慢池 + 盘中快筛** | 财报慢变量（市值/ROE/现金流/周期）隔夜算，行情快变量 15~30s 一轮，**抗反爬** |
| 📈 **开盘逐步入围** | 换手率 / 成交金额 / 内外比开盘未就绪时**自动跳过该项**，数据一到自动复筛 |
| 🩺 **空结果智能诊断** | 筛出 0 只时，自动告诉你「是哪个条件太严」（如「股息率淘汰 11 只」） |
| 🔌 **可插拔数据源** | 真实源（腾讯 + akshare + tushare）与 Mock 降级，环境变量一键切换 |
| 🐳 **多平台可运行** | Windows / macOS / Linux，支持本地 Python、Docker、Streamlit Cloud |

---

## 📋 筛选字段一览

共 **45 列**，分 8 组，全部 **2 位小数**、金额按「亿」换算（省略单位符号以节省宽度）、字号 15px（约 9pt），一屏容纳更多字段。

| 分组 | 字段 |
|---|---|
| **基础** | 代码、名称、二级行业、周期性 |
| **行情** | 现价、涨幅%、3 分钟涨速 |
| **资金** | 主力流速、超大单净额、大单净额、中单净额、小单净额 |
| **DDX** | 当日/5日/10日/20日 DDX、**主力增仓%双口径**（自由流通市值口径 + 成交额口径，×4 周期 = 8 列） |
| **盘口** | 内外比（= 内盘 ÷ 外盘，原始值实时算）、量比、换手率%、成交金额(亿) |
| **阶段** | 5/10/20/60 日涨幅%、近一年涨幅% |
| **估值** | 总市值(亿)、流通市值(亿)、市净率、PE(静)、PE(TTM)、PE(动) |
| **财务** | 净利润同比%、营业收入同比%、净资产收益率%、毛利率%、资产负债率%、股息率% |

> 主力增仓% 两种口径的含义：
> - **自由流通市值口径** `= 主力净额 ÷ 自由流通市值 × 100` —— 主指标，衡量「增仓强度」，跨市值可比（大市值股不会被大分母稀释）
> - **成交额口径** `= 主力净额 ÷ 当日总成交额 × 100` —— 辅指标，衡量「主力当天主导力」

---

## 🏗️ 核心架构

```
┌──────────────────────────────────────────────────┐
│  Level 1  季度慢池（财报级，天级 / 财报季按天重建）  │
│   沪深主板 ∩ 流通市值>100亿 ∩ ROE>5%               │
│   ∩ 现金流 ∩ 周期股过滤 ∩ PE/PB 均值比 ∩ PEG         │
│   → 候选池 50~300 只（财务字段只在这一层求一次）      │
└────────────────────┬─────────────────────────────┘
                     ↓ 只对候选池补盘口
┌──────────────────────────────────────────────────┐
│  Level 2  盘中快筛（行情级，15~30 秒 / 轮）         │
│   股价 ∩ 内外比 ∩ DDX ∩ 量比 ∩ 换手 ∩ 金额          │
│   ∩ 各类 PE/PB 均值比 ∩ 主力增仓%双口径             │
│   → curr - prev = ✅ 进入；prev - curr = ❌ 出局     │
└──────────────────────────────────────────────────┘
```

**为什么这样设计？** 全市场 5000+ 只股票若逐只抓财务/资金流，**必然触发反爬封禁**。把「变化慢的财报字段」放在慢池层隔夜算，「变化快的行情字段」在盘中轮询，能把接口压力降到 1/100。

---

## 🚀 快速开始（小白版）

### 方式一：本地 Python（推荐新手）

> 适合愿意装一次 Python 环境的人，Windows / macOS / Linux 都行。

**1. 安装 Python（3.9 及以上）**
- Windows / macOS：去 [python.org](https://www.python.org/downloads/) 下载安装，**勾选「Add to PATH」**
- Linux：`sudo apt install python3 python3-pip`

* 配置国内git源
```bash
pip config set global.index-url http://mirrors.aliyun.com/pypi/simple/
pip config set global.trusted-host mirrors.aliyun.com
```

**2. 下载本项目**
```bash
git clone https://github.com/Smopuim0913/RealTimeStockFilter.git
cd RealTimeStockFilter
```

**3. 安装依赖**
```bash
pip install -r requirements.txt
```
> Windows 用户若报权限错误，改用：`python -m pip install -r requirements.txt`

**4.（可选）配置数据 token**
复制配置模板，按需填入 tushare token（免费注册即得）：
```bash
cp .env.example .env
# 用记事本 / VS Code 打开 .env 编辑
```

**5. 启动**
```bash
streamlit run app.py
```
浏览器自动打开 `http://localhost:8501`，即可看到筛选表格。

**6. 切换真实 / 模拟数据**
在网页左侧边栏底部，或通过环境变量：
```bash
# 用真实行情（需有网络，tushare 部分字段需 token）
export DATASOURCE_MODE=real

# 用模拟数据演示（无需 token，离线可跑）
export DATASOURCE_MODE=mock
streamlit run app.py
```

---

### 方式二：Docker 一键（跨平台，免配环境）

> 适合不想装 Python、怕依赖冲突的人。只需装一次 Docker。

**1. 安装 Docker**
- Windows / macOS：[docker.com](https://www.docker.com/products/docker-desktop/) 下载 Docker Desktop
- Linux：`curl -fsSL get.docker.com | sh`

**2. 一行启动**
```bash
git clone https://github.com/Smopuim0913/RealTimeStockFilter.git
cd RealTimeStockFilter
cp .env.example .env   # 填 tushare token（可留空用 mock）

docker compose up -d --build
```
浏览器打开 `http://localhost:8501` 即可。

**停止：**
```bash
docker compose down
```

---

### 方式三：Streamlit Cloud（免安装，打开网页就用）

> 适合完全不想配环境的人。把本项目推到 GitHub 后：
> 1. 打开 [share.streamlit.io](https://share.streamlit.io)，用 GitHub 账号登录
> 2. 点「New app」→ 选本仓库 → 主文件路径填 `app.py`
> 3. 在「Advanced settings → Secrets」里粘贴 `TUSHARE_TOKEN = "你的token"`
> 4. 点 Deploy，几十秒后获得一个公网网址，发给别人也能打开

---

## ⚙️ 配置说明（`.env`）

复制 `.env.example` 为 `.env` 后按需修改：

| 变量 | 含义 | 默认值 |
|---|---|---|
| `DATASOURCE_MODE` | `real`（真实行情）/ `mock`（模拟数据） | `mock` |
| `TUSHARE_TOKEN` | tushare 访问 token（[注册地址](https://tushare.pro)） | 留空 |
| `REFRESH_SECONDS` | 盘中快筛刷新间隔（秒） | `20` |
| `POOL_REFRESH_HOURS` | 季度慢池重建间隔（小时） | `24` |

---

## 🎮 使用说明

### 1. 侧边栏控件

界面左侧是全部筛选条件，分 6 大类，改完**自动实时刷新**：

- **行情**：股价上限、内外比上限、量比下限、换手率下限、成交金额下限
- **DDX**：当日 / 5日 / 10日 / 20日 阈值
- **市值 / 估值**：流通市值、PB、PE(静/TTM/动)、PE(动/静)、PE(动/TTM) 比率、PEG
- **财务**：ROE、资产负债率、股息率
- **主力增仓%（双口径）**：当日/5/10/20 日的「自由流通市值口径」+「成交额口径」各一个阈值滑块
- **周期股过滤**：周期强度滑块（strong / mid_strong / mid / mid_weak / weak / none）+ 申万二级行业多选排除

### 2. 默认参数（宽松优先）

为保证**首次使用就有结果**，默认参数整体较宽松（如 DDX 默认不过滤、PE 上限 500），用户可逐步收紧到自己想要的强度。

### 3. 空结果诊断

当筛选结果为 **0 只**时，系统自动分析「是哪个条件太严」，在表格下方提示你放宽哪一项（例如「股息率淘汰 11 只、流通市值淘汰 8 只」），避免「一上来就 0 结果」的挫败感。

### 4. 列设置

- **拖动排序**：通过 multiselect 调整字段前后顺序
- **手动调宽**：每列宽度可通过 slider 微调
- **标题左对齐 / 数值右对齐**，标题字符宽度超出时截断显示（用单个 `.`）
- **进入 ✅ 绿色 / 出局 ❌ 红色**高亮闪烁

---

## 📊 数据来源与字段实现状态

| 字段组 | 数据源 | 获取方式 | 状态 |
|---|---|---|---|
| 盘口快变量（现价/涨幅/量比/换手/金额/PE静TTM动/PB） | 腾讯行情接口 / `akshare.stock_zh_a_spot_em` | 全市场一次快照（15~30s） | ✅ 已实现 |
| **内外比** | 腾讯行情接口（内盘 f161 / 外盘 f162） | 候选池补取，实时计算 `内盘÷外盘` | ✅ 已实现 |
| 主力/超大/大/中/小单净额、当日 DDX | `akshare.stock_individual_fund_flow` / 东财资金流 | 候选池补取（5 分钟缓存） | 🟡 部分（需接口稳定） |
| 5/10/20 日 DDX、主力增仓% | 历史资金流累加 | 开盘前预计算 + 盘中缓存 | 🟡 框架就绪，数据待补齐 |
| 60日 / 近一年涨幅 | `akshare.stock_zh_a_hist` 日线 | 每天开盘前算一次 | 🟡 待接入 |
| 财务慢变量（净利润同比/ROE/毛利率/资产负债率/股息率/营收同比） | `tushare.daily_basic` + `fina_indicator` | 季度慢池层 | 🟡 需 tushare token |
| 自由流通市值 | `tushare.daily_basic`（free_share）× 现价 | 慢池层一次性抓取 | 🟡 需 tushare token |
| 3 分钟涨速、主力流速 | `akshare.stock_zh_a_minute` | 候选池补取 | ⚪ 待实现 |

> 图例：✅ 已实现 ｜ 🟡 部分 / 依赖外部 ｜ ⚪ 待实现（欢迎 PR）
>
> **当前默认 `mock` 模式可离线完整演示全部 45 列与筛选逻辑**；切换 `real` 后，快变量与内外比已可真实获取，财务/资金流字段需 tushare token 并在网络允许下逐步补齐。

---

## 📁 文件结构

```
RealTimeStockFilter/
├── app.py              # Streamlit 前端主程序（界面 + 侧边栏控件 + 实时刷新）
├── cycle_engine.py     # 核心引擎：列配置 / 双口径增仓% / 快筛 / 诊断（可独立测试）
├── cycle_filter.py     # 周期股过滤模块：申万行业分级 + 周期性评分模型
├── data_source.py      # 可插拔数据源：真实(腾讯+akshare+tushare) / Mock 降级
├── test_*.py           # 各模块单元测试与需求点验证
├── requirements.txt    # Python 依赖清单
├── Dockerfile          # Docker 镜像定义（多平台一键运行）
├── docker-compose.yml  # Docker 编排（一键启动 + 环境变量）
├── .env.example        # 配置模板（token / 刷新间隔 / 数据源开关）
├── run.sh              # 本地启动脚本
└── README.md           # 本文件
```

---

## ❓ 常见问题（FAQ）

**Q：我不会写代码，能用吗？**
能。按「快速开始」装好环境后，只需在网页左侧拖动滑块改条件、点保存即可，不用改任何代码。

**Q：为什么有的字段显示为空 / 慢慢才出现？**
开盘前 5~30 分钟，换手率、成交金额、内外比累积量很小，比值噪声大。**系统对空值自动跳过该项**，等数据充分后自动「入围」，这是有意设计。

**Q：数据是实时的吗？**
腾讯/akshare 是**准实时快照（约 10~30 秒）**，不是毫秒级推送。做看盘 / 选股 / 预警足够；做实盘高频交易不够（那需要券商 QMT / 商业行情 API）。

**Q：会被封 IP 吗？**
程序已做防护：**全市场快照粗筛 → 只对候选池补盘口**，财务字段隔夜算、资金流带缓存。请勿自行改成「5000 只逐只高频循环」，否则必触发反爬。

**Q：需要付费吗？**
akshare + 腾讯接口免费；tushare **免费档**有频次/字段限制，注册即得 token，足够个人使用。不要用付费数据做商业分发。

**Q：为什么默认参数这么宽松？**
为保证首次使用就有结果（银行/保险/家电/贵金属等），你再按自己策略逐步收紧阈值即可。

---

## 🗺️ 路线图（Roadmap）

按优先级排序，欢迎认领：

- [ ] 接 `akshare.stock_zh_a_spot_em` 真实全市场快照，替换 mock 盘口
- [ ] tushare `daily_basic` 补 PE/TTM/市值/利润同比/股息/自由流通股本
- [ ] 东财资金流补当日/5/10/20 日 DDX 与主力净额（含 `stock_individual_fund_flow` 批量优化）
- [ ] 内外比用内盘/外盘原始值实时计算（框架已就绪，待联调验证）
- [ ] 3 分钟涨速、主力流速（分钟级数据）
- [ ] 多平台安装文档实测（Windows 一键 `.bat` / macOS `brew` / Linux `apt`）
- [ ] Dockerfile + docker-compose（实现中）
- [ ] 界面截图 / 30 秒操作 GIF
- [ ] 默认参数组合预设（稳健型 / 激进型 / 盘口型）
- [ ] 支持科创板/创业板/北交所（当前默认沪深主板）
- [ ] 告警推送（企业微信 / 钉钉 / 邮件）

---

## 🤝 如何参与贡献（求大佬 PR）

> 作者是编程新手，非常欢迎懂 `Python` / `akshare` / `tushare` / `Streamlit` / `Docker` 的朋友来帮忙！
> 哪怕不会写代码，也可以通过「提 issue / 写文档 / 录截图」参与。

### 贡献方式

**代码贡献：**
1. Fork 本仓库 → 新建分支 `git checkout -b feature/xxx`
2. 提交改动 → `git commit -m "feat: 实现 xxx"`
3. 推送到你的 Fork → 发起 Pull Request

**非代码贡献（同样欢迎）：**
- 补充 Windows / macOS / Linux 安装实测步骤
- 截图 / 录 30 秒操作 GIF
- 整理默认参数组合（稳健型 / 激进型 / 盘口型）
- 整理申万二级行业排除清单
- 写「小白用户常见问题」
- 测试并反馈 bug

### 适合新手的 Issue

请认领打有 `good first issue` / `documentation` / `enhancement` / `bug` 标签的任务。建议先看：

- [ ] 加 `Dockerfile` 与 `docker-compose.yml`
- [ ] 把 mock 数据切换为 akshare 真实快照
- [ ] tushare `daily_basic` 字段映射补全
- [ ] 东财资金流补 DDX 与主力净额
- [ ] Windows / macOS 安装文档实测

提交 PR 前请先开一个 issue 说明你想做的事，避免重复劳动。

---

## ⚠️ 免责声明

- 本项目仅供 **学习与技术研究**，所涉及的行情接口均为公开数据，**不构成任何投资建议**。
- 筛选结果**不等于买卖信号**，据此操作风险自担。
- 请遵守数据源（东方财富、腾讯、Tushare）的 **使用条款与频率限制**，勿高频并发抓取。
- 本项目与任何券商、数据商**无官方合作关系**。

---

## 📄 License

[MIT License](./LICENSE) © 2026 Smopuim0913

> 如果本项目对你有帮助，欢迎 ⭐ Star、提 Issue、发 PR —— 你的每一点反馈都是对开源新手最大的鼓励 🙌
