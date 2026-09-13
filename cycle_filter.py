"""
周期股过滤模块（V2）
==================================
设计目标：为"季度慢池 + 盘中快筛"架构增加「周期股过滤」能力。

核心思路：
1. 申万行业分级打标（静态映射表，成本几乎为零，覆盖 80% 场景）
2. 逐标的周期性评分（V2 增强，基于财务波动率，覆盖行业内分化）
3. 统一接口：get_cycle_strength() —— 供 SlowConditions.check() 调用

周期强度档位（5 档）：
    strong    强周期    —— 煤炭/有色/石油石化/钢铁/基础化工
    mid_strong 中强周期  —— 建材/建筑装饰/房地产
    mid       中周期     —— 交通运输/公用事业/机械设备/电力设备
    mid_weak  中弱周期   —— 汽车/农林牧渔/综合
    weak      弱周期     —— 其余消费/成长/公用事业细分
    none      无周期     —— 食品饮料/医药生物/银行等

控件建议（前端）：
    - 主控件：周期强度滑块（strong → none），默认 'mid_weak'
    - 辅助：申万二级行业多选排除树
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# =====================================================================
# 一、申万行业 → 周期强度 静态映射表
# =====================================================================
# 申万 2021 版：31 个一级 + 部分常用二级
# 格式：(申万一级代码, 二级代码 or None, 名称, 强度档位)

SW_CYCLE_MAP: List[Tuple[str, Optional[str], str, str]] = [
    # ---------- 强周期：上游资源 + 中游材料 ----------
    ('801050', None,   '有色金属',   'strong'),
    ('801020', None,   '煤炭',       'strong'),
    ('801060', None,   '石油石化',   'strong'),
    ('801040', None,   '钢铁',       'strong'),
    ('801030', None,   '基础化工',   'strong'),
    # 有色二级：贵金属/小金属偏弱，可单独降级（见精细覆盖）
    ('801050', '工业金属', '工业金属', 'strong'),
    ('801050', '贵金属',   '贵金属',   'mid_weak'),   # 避险属性，弱周期
    ('801050', '小金属',   '小金属',   'mid'),        # 新能源金属，成长属性
    ('801030', '农用化工', '农化制品', 'mid_strong'),

    # ---------- 中强周期：地产链 + 基建 ----------
    ('801070', None,   '建筑材料',   'mid_strong'),
    ('801710', None,   '建筑装饰',   'mid_strong'),
    ('801180', None,   '房地产',     'mid_strong'),

    # ---------- 中周期：制造 + 公用事业 ----------
    ('801740', None,   '机械设备',   'mid'),
    ('801730', None,   '电力设备',   'mid'),
    ('801170', None,   '交通运输',   'mid'),
    ('801160', None,   '公用事业',   'mid'),
    ('801150', None,   '医药生物',   'mid_weak'),  # 防御属性
    ('801140', None,   '轻工制造',   'mid'),

    # ---------- 中弱周期：可选消费 + 农业 ----------
    ('801880', None,   '汽车',       'mid_weak'),
    ('801010', None,   '农林牧渔',   'mid_weak'),  # 猪周期
    ('801200', None,   '商贸零售',   'mid_weak'),
    ('801130', None,   '纺织服饰',   'mid_weak'),
    ('801110', None,   '家用电器',   'mid_weak'),
    ('801080', None,   '电子',       'mid_weak'),  # 半导体有周期，但偏成长
    ('801750', None,   '计算机',     'weak'),
    ('801760', None,   '传媒',       'weak'),

    # ---------- 无周期：必选消费 + 金融 ----------
    ('801120', None,   '食品饮料',   'none'),
    ('801210', None,   '社会服务',   'none'),
    ('801230', None,   '综合',       'mid_weak'),
    ('801780', None,   '银行',       'none'),
    ('801790', None,   '非银金融',   'none'),
    ('801770', None,   '通信',       'weak'),
    ('801720', None,   '国防军工',   'mid'),
    ('801000', None,   '美容护理',   'none'),
    ('801690', None,   '有色金属',   'strong'),  # 兜底（同 801050）
]


# 强度 → 数值（越大越周期）
STRENGTH_RANK = {
    'none': 0,
    'weak': 1,
    'mid_weak': 2,
    'mid': 3,
    'mid_strong': 4,
    'strong': 5,
}


@dataclass
class CycleTag:
    """单只股票的周期标签结果"""
    code: str
    sw_l1_code: str = ''
    sw_l1_name: str = ''
    sw_l2_name: str = ''
    industry_strength: str = 'mid'   # 行业打标强度
    score_strength: str = 'mid'      # 财务评分强度（V2）
    final_strength: str = 'mid'      # 取两者 max
    score: float = 0.0              # 0~1 量化分


class CycleClassifier:
    """周期股分类器：申万行业打标 + 周期性评分"""

    def __init__(self, score_cache: Optional[Dict[str, float]] = None):
        """
        Parameters
        ----------
        score_cache : dict, optional
            逐标的周期性评分缓存 {code: score(0~1)}
            由 build_cycle_scores() 离线计算，启动时加载
        """
        self._l1_map: Dict[str, str] = {}      # l1_code -> strength
        self._l2_map: Dict[Tuple[str, str], str] = {}  # (l1, l2) -> strength
        self._code_l1: Dict[str, str] = {}     # code -> l1_name（需外部注入）
        self._code_l2: Dict[str, str] = {}     # code -> l2_name
        self.score_cache = score_cache or {}

        self._build_maps()

    # ---------- 初始化映射表 ----------
    def _build_maps(self):
        for l1_code, l2, name, strength in SW_CYCLE_MAP:
            if l2 is None:
                self._l1_map[l1_code] = strength
            else:
                self._l2_map[(l1_code, l2)] = strength

    def load_industry_mapping(self, code_l1: Dict[str, str], code_l2: Dict[str, str]):
        """注入 代码→申万行业 映射（来自 Tushare stock_basic / 本地缓存）"""
        self._code_l1 = code_l1
        self._code_l2 = code_l2

    # ---------- 主接口 ----------
    def classify(self, code: str) -> CycleTag:
        """返回单只股票的周期标签"""
        l1_name = self._code_l1.get(code, '')
        l2_name = self._code_l2.get(code, '')
        l1_code = self._name_to_l1_code(l1_name)

        # 1) 行业打标：优先二级，回退一级
        strength = self._l1_map.get(l1_code, 'mid')
        if l2_name:
            strength = self._l2_map.get((l1_code, l2_name), strength)

        # 2) 财务评分（V2，若有缓存则取 max）
        score = self.score_cache.get(code, 0.0)
        score_strength = score_to_strength(score)
        if STRENGTH_RANK[score_strength] > STRENGTH_RANK[strength]:
            strength = score_strength

        return CycleTag(
            code=code,
            sw_l1_code=l1_code,
            sw_l1_name=l1_name,
            sw_l2_name=l2_name,
            industry_strength=strength,
            score_strength=score_strength,
            final_strength=strength,
            score=score,
        )

    # ---------- 工具 ----------
    def _name_to_l1_code(self, name: str) -> str:
        for l1_code, _, n, _ in SW_CYCLE_MAP:
            if n == name:
                return l1_code
        return ''

    def get_strength(self, code: str) -> str:
        return self.classify(code).final_strength

    def is_allowed(self, code: str, max_strength: str = 'mid_weak') -> bool:
        """是否满足周期强度上限（用于 SlowConditions.check）"""
        strength = self.get_strength(code)
        return STRENGTH_RANK[strength] <= STRENGTH_RANK[max_strength]


# =====================================================================
# 二、周期性评分模型（V2，离线计算）
# =====================================================================
# 基于过去 N 年财报波动率：
#   - 毛利率波动率（std/mean）>30% 强周期
#   - 净利润波动率              >100% 强周期
#   - 股价 vs 商品/宏观 相关系数   >0.7 强周期

def score_to_strength(score: float) -> str:
    """量化分 0~1 → 强度档位"""
    if score >= 0.75:
        return 'strong'
    elif score >= 0.60:
        return 'mid_strong'
    elif score >= 0.45:
        return 'mid'
    elif score >= 0.30:
        return 'mid_weak'
    elif score >= 0.15:
        return 'weak'
    return 'none'


def build_cycle_scores(financial_history: Dict[str, dict]) -> Dict[str, float]:
    """
    离线计算全市场周期性评分（季报期跑一次即可）

    Parameters
    ----------
    financial_history : {code: {'gross_margin': [...], 'net_profit': [...], 'beta': float}}

    Returns
    -------
    {code: score(0~1)}
    """
    import numpy as np

    scores = {}
    for code, hist in financial_history.items():
        gm = np.array(hist.get('gross_margin', []), dtype=float)
        npf = np.array(hist.get('net_profit', []), dtype=float)
        beta = hist.get('beta', 0.0)

        # 毛利率波动率
        gm_cv = np.std(gm) / (np.mean(np.abs(gm)) + 1e-9) if len(gm) > 1 else 0
        # 净利润波动率（用变异系数）
        npf_cv = np.std(npf) / (np.mean(np.abs(npf)) + 1e-9) if len(npf) > 1 else 0

        # 三项归一化
        s_gm = min(gm_cv / 0.30, 1.0)      # 30% → 1.0
        s_npf = min(npf_cv / 1.00, 1.0)    # 100% → 1.0
        s_beta = min(abs(beta) / 0.7, 1.0) # 0.7  → 1.0

        score = 0.35 * s_gm + 0.45 * s_npf + 0.20 * s_beta
        scores[code] = round(float(score), 3)

    return scores


# =====================================================================
# 三、与 SlowConditions 的集成示例
# =====================================================================

@dataclass
class SlowConditionsWithCycle:
    """在原有慢条件基础上增加周期过滤"""
    # ... 原有字段省略，仅展示新增部分 ...
    max_cycle_strength: str = 'mid_weak'   # 最大允许周期强度
    excluded_sw_l2: List[str] = field(default_factory=lambda: [
        '工业金属', '石油开采', '普钢', '煤炭开采'
    ])

    # 依赖注入：分类器单例
    cycle_classifier: Optional[CycleClassifier] = None

    def check(self, stock) -> bool:
        # ... 其他条件省略 ...
        if self.cycle_classifier is None:
            return True

        tag = self.cycle_classifier.classify(stock.code)

        # 1) 周期强度上限
        if STRENGTH_RANK[tag.final_strength] > STRENGTH_RANK[self.max_cycle_strength]:
            return False

        # 2) 申万二级精细排除
        if tag.sw_l2_name in self.excluded_sw_l2:
            return False

        return True


# =====================================================================
# 四、演示与自测
# =====================================================================

@dataclass
class _FakeStock:
    """演示用股票对象（真实环境换成你的 Stock dataclass）"""
    code: str


if __name__ == '__main__':
    print("=" * 60)
    print("周期股过滤模块 —— 演示 & 自测")
    print("=" * 60)

    # 模拟 代码→申万行业 映射（真实环境由 Tushare stock_basic 注入）
    code_l1 = {
        '600188': '煤炭',
        '601899': '有色金属',
        '600028': '石油石化',
        '600019': '钢铁',
        '600309': '基础化工',
        '600585': '建筑材料',
        '000002': '房地产',
        '600036': '银行',
        '600519': '食品饮料',
        '300750': '电力设备',
        '600104': '汽车',
        '601318': '非银金融',
    }
    code_l2 = {
        '601899': '贵金属',      # 有色 → 但二级贵金属降级为 mid_weak
        '600028': '石油开采',    # 二级精细排除
    }

    # 模拟财务评分缓存（V2）
    score_cache = {
        '600188': 0.85,   # 煤炭，财务评分极高 → strong
        '600519': 0.10,   # 茅台，防御 → none
        '300750': 0.55,   # 宁德，成长但财务波动 → mid
    }

    clf = CycleClassifier(score_cache=score_cache)
    clf.load_industry_mapping(code_l1, code_l2)

    print("\n【1】行业打标 + 财务评分 联合结果：")
    print(f"{'代码':<8}{'名称':<10}{'L1':<10}{'L2':<10}{'行业档':<10}{'评分档':<10}{'最终':<10}{'评分'}")
    print("-" * 86)
    for code, name in code_l1.items():
        tag = clf.classify(code)
        print(f"{code:<8}{name:<10}{tag.sw_l1_name:<10}{tag.sw_l2_name or '-':<10}"
              f"{tag.industry_strength:<10}{tag.score_strength:<10}{tag.final_strength:<10}{tag.score}")

    print("\n【2】周期强度过滤测试（max_strength='mid_weak'）：")
    cond = SlowConditionsWithCycle(max_cycle_strength='mid_weak', cycle_classifier=clf)
    allowed, blocked = [], []
    for code in code_l1:
        (allowed if cond.check(_FakeStock(code)) else blocked).append(code)
    print(f"  ✅ 通过（非强/中强周期）：{allowed}")
    print(f"  ❌ 拦截（强/中强周期）：{blocked}")

    print("\n【3】申万二级精细排除测试：")
    tag_028 = clf.classify('600028')
    ok = cond.check(_FakeStock('600028'))
    print(f"  600028 石油石化/石油开采 → 最终档 {tag_028.final_strength}")
    print(f"  '石油开采' 在排除列表 → is_allowed = {ok}")

    print("\n【4】评分模型单元测试：")
    fake_hist = {
        'A': {'gross_margin': [0.3, 0.28, 0.32, 0.29], 'net_profit': [10, 11, 9, 12], 'beta': 0.3},
        'B': {'gross_margin': [0.5, 0.1, 0.6, 0.05], 'net_profit': [5, -2, 20, -8], 'beta': 0.9},
    }
    scores = build_cycle_scores(fake_hist)
    print(f"  A（稳定，应弱周期）：score={scores['A']} → {score_to_strength(scores['A'])}")
    print(f"  B（剧烈波动，应强周期）：score={scores['B']} → {score_to_strength(scores['B'])}")

    # ---------- 断言验证 ----------
    assert clf.classify('600188').final_strength == 'strong', "煤炭应为 strong"
    assert clf.classify('601899').final_strength == 'mid_weak', "贵金属应降级为 mid_weak"
    assert clf.classify('600519').final_strength == 'none', "白酒应为 none"
    assert not cond.check(_FakeStock('600028')), "石油开采应被二级排除"
    assert cond.check(_FakeStock('600036')), "银行应通过"
    assert scores['B'] > scores['A'], "波动大的 B 评分应高于 A"
    print("\n" + "=" * 60)
    print("✅ 全部断言通过")
    print("=" * 60)
