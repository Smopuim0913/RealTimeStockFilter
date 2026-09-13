# -*- coding: utf-8 -*-
"""
通达信/同花顺中文表头 manual_pool.csv → 系统标准英文表头手动慢池
- 自动探测编码 (UTF-8 / GBK / GB2312 / UTF-8-SIG)，解决 Windows Excel 导出乱码
- 自动备份原文件为 manual_pool.csv.bak
用法: python convert_manual_pool.py
"""
import csv
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SRC = BASE_DIR / "manual_pool.csv"
BAK = BASE_DIR / "manual_pool.csv.bak"

# 尝试的编码顺序（Windows 中文环境 Excel 默认 GBK，Mac/网页多为 UTF-8）
ENCODINGS = ["utf-8-sig", "utf-8", "gb18030", "gbk", "gb2312"]


def read_csv_rows(path: Path):
    """自动探测编码并读取为 (fieldnames, rows)"""
    raw = path.read_bytes()
    # 优先用 chardet（若已装）做启发式探测
    detected = None
    try:
        import chardet
        detected = chardet.detect(raw).get("encoding")
    except Exception:
        pass

    candidates = list(ENCODINGS)
    if detected and detected.lower() not in [c.lower() for c in ENCODINGS]:
        candidates = [detected] + candidates

    last_err = None
    for enc in candidates:
        try:
            text = raw.decode(enc, errors="strict")
            reader = csv.DictReader(text.splitlines())
            fieldnames = reader.fieldnames
            if not fieldnames:
                continue
            rows = [r for r in reader if any(v and v.strip() for v in r.values())]
            print(f"✅ 编码探测成功: {enc}")
            return fieldnames, rows
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"无法解码 {path}，尝试过 {candidates}，最后错误: {last_err}")


# 中文表头 → 系统标准字段 映射
COLUMN_MAP = {
    "代码": "code", "名称": "name", "所属行业": "sw_l2",
    "加权净资产收益率": "roe", "归属净利润同比": "profit_yoy",
    "营业收入同比": "rev_yoy", "销售毛利率": "gross_margin",
    "资产负债比率": "debt_ratio",
    "市净率": "pb", "市盈率(静)": "pe_static", "市盈率(动)": "pe_dyn",
    "总市值": "total_mv", "流通市值": "circ_mv",
    # 额外保留字段
    "每股收益": "eps", "每股净资产": "bvps",
    "每股公积金": "capital_reserve", "每股未分配利润": "undist_profit",
}


def normalize_key(s: str) -> str:
    """表头归一化：去空格、中文括号→英文、全角→半角，便于模糊匹配"""
    if not s:
        return ""
    s = s.strip()
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("\u3000", " ")
    return s


def main():
    if not SRC.exists():
        print(f"❌ 未找到 {SRC}，请把它放到项目根目录。")
        sys.exit(1)

    shutil.copy2(SRC, BAK)
    print(f"✅ 原文件已备份至 {BAK}")

    fieldnames, rows = read_csv_rows(SRC)

    # 建归一化索引（兼容表头带空格/括号差异）
    norm_map = {normalize_key(fn): fn for fn in fieldnames}

    def find_col(cn: str):
        """精确 → 归一化 → 包含匹配"""
        if cn in fieldnames:
            return cn
        nk = normalize_key(cn)
        if nk in norm_map:
            return norm_map[nk]
        # 包含匹配（如 CSV 里是 "加权净资产收益率(%)"）
        for k in fieldnames:
            if cn in k or k in cn:
                return k
        return None

    # 校验必要列
    missing = [cn for cn in ["代码", "名称", "所属行业"] if not find_col(cn)]
    if missing:
        print(f"❌ 未找到必要列: {missing}")
        print(f"   当前表头: {list(fieldnames)}")
        sys.exit(1)

    converted = []
    for raw in rows:
        new_row = {}
        for cn, en in COLUMN_MAP.items():
            col = find_col(cn)
            val = raw.get(col) if col else None
            if val is not None:
                val = val.strip()
            new_row[en] = val if val else ""
        converted.append(new_row)

    # 统一写出为 UTF-8-SIG（Excel 打开也正常，Streamlit 读取无乱码）
    fieldnames_out = list(COLUMN_MAP.values())
    with open(SRC, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames_out)
        writer.writeheader()
        writer.writerows(converted)

    print(f"🎉 转换完成！共 {len(converted)} 只股票")
    print("已映射字段:")
    for cn, en in COLUMN_MAP.items():
        print(f"  {cn}  →  {en}")
    print(f"\n输出编码: utf-8-sig（可被 Excel / Streamlit 正常读取）")


if __name__ == "__main__":
    main()