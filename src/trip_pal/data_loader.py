"""数据读取层：把 data/ 下的 JSON 加载为工具可用的结构。

设计意图：
  - 运行时只读本地 JSON，不碰网络（稳定、可测、尊重数据源）；
  - 提供统一的查询接口，工具层不关心数据文件细节；
  - 将来若换实时数据源，只需改这个模块，不影响 tools / graph。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .config import settings

# 数据结构说明（与 fetch_data.py 输出一致）：
#   香港: {"year": 2027, "region": "hk", "holidays": [
#            {"name": "一月一日", "date": "2027-01-01", "weekday": "星期五"}, ... ]}
#   内地: {"year": 2026, "region": "cn", "holidays": [
#            {"name": "元旦", "start": "2026-01-01", "end": "2026-01-03",
#             "detail": "...", "makeup_workdays": ["2026-01-04"]}, ... ]}


def _load_region(region: str, year: int) -> dict | None:
    """读取单个 region+year 的 JSON；文件不存在返回 None。"""
    path: Path = settings.data_dir / f"holidays_{region}_{year}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_hk_holidays(year: int) -> list[dict]:
    """返回香港某年的公众假期列表（空列表若无数据）。"""
    data = _load_region("hk", year)
    return data["holidays"] if data else []


def get_cn_holidays(year: int) -> list[dict]:
    """返回内地某年的节假日（含调休）列表（空列表若无数据）。"""
    data = _load_region("cn", year)
    return data["holidays"] if data else []


def available_years(region: str) -> list[int]:
    """返回某 region 已有哪些年份的数据（用于提示模型可用范围）。"""
    years: list[int] = []
    for path in (settings.data_dir).glob(f"holidays_{region}_*.json"):
        try:
            years.append(int(path.stem.split("_")[-1]))
        except ValueError:
            continue
    return sorted(years)


def is_workday_cn(d: date, year: int) -> bool:
    """判断内地某日是否工作日（考虑节假日与调休上班日）。

    判断顺序很关键（后面的判断会覆盖前面的）：
      1. 先按自然周判（周一至五 = 工作日）；
      2. 再判节假日 → 若在放假期内则改为非工作日；
      3. 最后判调休上班日 → 若为补班日则改回工作日。
    顺序不可调换：调休上班日（如国庆后的周六）必须最后判，
    才能覆盖"周末 + 节假日"的判定。
    """
    # 1) 基础：周一至五为工作日
    workday = d.weekday() < 5

    # 2) 节假日期间不算工作日
    holidays = get_cn_holidays(year)  # 只读一次
    for h in holidays:
        start = date.fromisoformat(h["start"])
        end = date.fromisoformat(h["end"])
        if start <= d <= end:
            workday = False

    # 3) 调休上班日（周末补班）算工作日 —— 最后判断以覆盖前两步
    for h in holidays:
        if d.isoformat() in h.get("makeup_workdays", []):
            workday = True
    return workday
