# -*- coding: utf-8 -*-
"""
本地缓存：规避 TuShare 1次/小时限流（免费积分）
- 慢池(pool)：日级，缓存 12 小时
- 快照(snapshot)：盘中级，缓存 5 分钟
重启/换代码不丢数据；过期自动重取，取不到则用过期缓存（保证界面不断流）
"""
import os
import json
import time
from pathlib import Path

CACHE_DIR = Path(os.getenv("CACHE_DIR", Path(__file__).parent / ".cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

TTL = {
    "pool": 12 * 3600,       # 慢池 12 小时
    "snapshot": 5 * 60,      # 快照 5 分钟
}


def _path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def get(key: str):
    p = _path(key)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    age = time.time() - data.get("ts", 0)
    if age > TTL.get(key, 3600):
        return None
    return data.get("value")


def put(key: str, value):
    _path(key).write_text(
        json.dumps({"ts": time.time(), "value": value}, ensure_ascii=False),
        encoding="utf-8",
    )


def get_stale(key: str):
    """过期也可用（限流时兜底，保证界面有数据）"""
    p = _path(key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("value")
    except Exception:
        return None


def age_str(key: str) -> str:
    p = _path(key)
    if not p.exists():
        return "无缓存"
    try:
        ts = json.loads(p.read_text(encoding="utf-8")).get("ts", 0)
    except Exception:
        return "损坏"
    secs = time.time() - ts
    if secs < 60:
        return f"{int(secs)}秒前"
    if secs < 3600:
        return f"{int(secs/60)}分钟前"
    return f"{int(secs/3600)}小时前"
