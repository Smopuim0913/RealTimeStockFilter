"""
可插拔数据源：真实行情(akshare/tushare) 与 Mock 模拟数据自动切换
用法：
    os.environ['USE_REAL_DATA'] = 'True'
    os.environ['TUSHARE_TOKEN'] = '你的token'
    ds = DataSource()
    df = ds.get_snapshot()   # 返回 DataFrame，字段与 MOCK 一致
"""

import os
import time
import pandas as pd

# 尝试导入真实数据源（没有装也可以用 mock 运行）
try:
    import akshare as ak
    _HAS_AKSHARE = True
except ImportError:
    _HAS_AKSHARE = False

try:
    import tushare as ts
    _HAS_TUSHARE = True
except ImportError:
    _HAS_TUSHARE = False


class DataSource:
    def __init__(self):
        # 是否使用真实数据（环境变量控制，默认 False 自动用 mock）
        self.use_real = os.getenv('USE_REAL_DATA', 'False').lower() in ('true', '1', 'yes')
        self.token = os.getenv('TUSHARE_TOKEN', '')

        # 启动时打印当前模式
        if self.use_real:
            if not _HAS_AKSHARE and not _HAS_TUSHARE:
                print("[提示] 已设置 USE_REAL_DATA=True 但未安装 akshare/tushare，自动降级 Mock")
                self.use_real = False
            elif not self.token:
                print("[警告] 已设置 USE_REAL_DATA=True 但缺少 TUSHARE_TOKEN，财报字段将为 None，行情仍走真实")
            else:
                print("[信息] 使用真实数据模式")
        else:
            print("[信息] 使用 MOCK 模拟数据模式（可通过设置环境变量 USE_REAL_DATA=True 切换）")

    # ========== 对外统一接口 ==========

    def get_snapshot(self, columns_map=None):
        """
        返回全市场快照 DataFrame，字段与 MOCK 保持一致。
        真实源：akshare stock_zh_a_spot_em（约23个标准字段）
        """
        if not self.use_real or not _HAS_AKSHARE:
            return self._mock_snapshot()

        try:
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                print("[警告] akshare 返回空数据，降级 Mock")
                return self._mock_snapshot()

            # 重命名为项目内部统一字段（映射关系）
            rename_map = {
                '代码': 'code',
                '名称': 'name',
                '最新价': 'price',
                '涨跌幅': 'pct_chg',
                '成交量': 'volume',
                '成交额': 'amount',
                '换手率': 'turnover',
                '市盈率-动态': 'pe_dynamic',
                '市净率': 'pb',
                '总市值': 'total_mv',
                '流通市值': 'circ_mv',
            }
            df = df.rename(columns=rename_map)
            df = df[[c for c in rename_map.values() if c in df.columns]]

            # 数值转为 float，缺字段置 None
            for col in ['price', 'pct_chg', 'volume', 'amount', 'turnover',
                        'pe_dynamic', 'pb', 'total_mv', 'circ_mv']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                else:
                    df[col] = None

            # 补充 tushare 财务字段（若 token 已配置）
            if self.token and _HAS_TUSHARE:
                df = self._add_ts_financials(df)

            return df

        except Exception as e:
            print(f"[错误] 获取真实快照失败：{e}，降级 Mock")
            return self._mock_snapshot()

    def _add_ts_financials(self, df):
        """从 tushare daily_basic 补充 PE-TTM / 自由流通市值 / 利润同比 等慢变量"""
        try:
            pro = ts.pro_api(self.token)
            trade_date = pro.trade_cal(exchange='', start_date='', end_date='', is_open='1')['cal_date'].max()
            basic = pro.daily_basic(
                ts_code='',
                trade_date=trade_date,
                fields='ts_code,close,pe_ttm,pb,total_mv,circ_mv,free_share'
            )
            basic = basic.rename(columns={
                'ts_code': 'ts_code',
                'pe_ttm': 'pe_ttm',
                'free_share': 'free_share'
            })
            # 注意：tushare 的代码是 600000.SH 格式，需要转成 600000
            basic['code6'] = basic['ts_code'].str[:6]
            if 'code' not in df.columns:
                df['code'] = df['code'].astype(str).str.zfill(6)
            df = df.merge(basic[['code6', 'pe_ttm', 'free_share']],
                          left_on='code', right_on='code6', how='left')
            # 自由流通市值 = 自由流通股本 * 现价
            if 'free_share' in df.columns and 'price' in df.columns:
                df['free_circ_mv'] = df['free_share'] * df['price'] / 1e8
            df.drop(columns=['code6'], errors='ignore', inplace=True)
            return df
        except Exception as e:
            print(f"[错误] tushare 补充财务字段失败：{e}")
            return df

    # ========== Mock 模拟数据 ==========

    def _mock_snapshot(self):
        """生成与 MOCK 同结构的模拟数据（含周期/资金双口径字段示例）"""
        base_data = [
            # code, name, price, pct_chg, volume, amount, turnover, pe_dynamic, pb, total_mv, circ_mv
            ('600547', '山东黄金', 28.50, 1.2, 1250000, 35.6e8, 0.8, 35.2, 3.1, 1200e8, 980e8),
            ('601398', '工商银行', 5.80, 0.4, 2300000, 13.3e8, 0.3, 6.1, 0.7, 21000e8, 20500e8),
            ('600519', '贵州茅台', 1600.00, 0.1, 42000, 67.0e8, 0.2, 30.5, 8.2, 19000e8, 19000e8),
            ('000001', '平安银行', 12.30, 0.7, 1650000, 20.3e8, 1.2, 7.8, 0.9, 2300e8, 2250e8),
            ('600036', '招商银行', 55.20, -0.2, 780000, 43.1e8, 0.6, 7.2, 1.1, 14000e8, 13800e8),
        ]
        cols = ['code', 'name', 'price', 'pct_chg', 'volume', 'amount',
                'turnover', 'pe_dynamic', 'pb', 'total_mv', 'circ_mv']
        df = pd.DataFrame(base_data, columns=cols)

        # 构造自由流通市值
        df['free_circ_mv'] = df['circ_mv'] * [0.9, 0.3, 0.8, 0.7, 0.85]

        # 慢变量
        df['pe_ttm'] = [38.0, 5.9, 31.0, 7.5, 7.0]
        df['profit_yoy'] = [45.0, -3.0, 15.0, 3.0, 9.0]
        df['roe'] = [12.0, 11.0, 28.0, 13.0, 14.0]
        df['debt_ratio'] = [45.0, 88.0, 20.0, 92.0, 90.0]
        df['dividend_yield'] = [0.8, 5.5, 2.3, 2.5, 4.2]
        df['main_net_amount'] = [1.2e8, 0.8e8, 2.0e8, 0.5e8, 1.0e8]
        return df


# ========== 独立测试：直接运行本文件查看效果 ==========
if __name__ == '__main__':
    ds = DataSource()
    snapshot = ds.get_snapshot()
    print("快照返回行数：", len(snapshot))
    print(snapshot.head())
    print("字段列表：", list(snapshot.columns))