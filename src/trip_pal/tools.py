"""工具集：TripPal Agent 的「手」。

这是 Agent 能力的关键：模型不能直接碰数据，只能通过这里的工具。
每个工具必须「自描述」——函数名、docstring、类型注解，都会被 LangChain
转成模型能读的 JSON Schema（工具的「说明书」）。工具写得好不好，
直接决定模型能不能正确调用它。

设计铁律：
  1. 自描述：docstring 写清「干什么、参数、何时用」；
  2. 参数结构化：类型注解 + Optional/默认值，表达必填/可选；
  3. 返回结构化：返回 JSON 友好的 dict，让模型容易读；
  4. 边界安全：只读查询，不写数据。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from langchain_core.tools import tool

from .data_loader import get_cn_holidays, get_hk_holidays, available_years


# ---------------------------------------------------------------------------
# 工具 1：查内地节假日
# ---------------------------------------------------------------------------
@tool
def get_holidays_cn(year: int, month: int | None = None) -> dict:
    """查询中国内地（大陆）某年的法定节假日安排。

    返回该年（或该月）的节假日列表，含放假起止日期和调休上班日。

    Args:
        year: 年份，如 2026。支持 2025、2026（2027 待官方发布）。
        month: 可选，只返回该月（1-12）的节假日；缺省返回全年。
    """
    holidays = get_cn_holidays(year)
    if not holidays:
        return {
            "year": year,
            "note": f"暂无 {year} 年内地节假日数据（2027 年安排尚未发布）",
            "holidays": [],
        }
    if month is not None:
        holidays = [
            h for h in holidays
            if int(h["start"][5:7]) == month or int(h["end"][5:7]) == month
        ]
    return {"year": year, "region": "cn", "holidays": holidays}


# ---------------------------------------------------------------------------
# 工具 2：查香港公众假期
# ---------------------------------------------------------------------------
@tool
def get_holidays_hk(year: int, month: int | None = None) -> dict:
    """查询香港公众假期。

    返回该年（或该月）的公众假期列表，含日期和星期。

    Args:
        year: 年份，如 2027。支持 2025、2026、2027。
        month: 可选，只返回该月（1-12）的公众假期；缺省返回全年。
    """
    holidays = get_hk_holidays(year)
    if not holidays:
        return {
            "year": year,
            "note": f"暂无 {year} 年香港公众假期数据",
            "holidays": [],
        }
    if month is not None:
        holidays = [h for h in holidays if int(h["date"][5:7]) == month]
    return {"year": year, "region": "hk", "holidays": holidays}


# ---------------------------------------------------------------------------
# 工具 3：找两地共同/接近的假期窗口
# ---------------------------------------------------------------------------
@tool
def find_common_breaks(year: int) -> dict:
    """找出香港与内地某一年「共同或接近重叠」的长假期窗口。

    用于回答如「内地和香港下个共同长假期是什么时候」这类问题。
    规则：两地假期各自放假 ≥3 天，且放假区间有至少 1 天重叠，
    视为一个「共同假期窗口」。

    Args:
        year: 年份，如 2026。
    """
    hk = get_hk_holidays(year)
    cn = get_cn_holidays(year)
    if not hk or not cn:
        return {"year": year, "note": "两地数据不齐，无法计算共同假期", "windows": []}

    # 香港是单日假期，把连续日期合并成区间（方便和内地区间比较）
    hk_dates = sorted(date.fromisoformat(h["date"]) for h in hk)
    hk_ranges: list[tuple[date, date]] = []
    for d in hk_dates:
        if hk_ranges and hk_ranges[-1][1] + timedelta(days=1) >= d:
            hk_ranges[-1] = (hk_ranges[-1][0], d)
        else:
            hk_ranges.append((d, d))

    windows: list[dict] = []
    for h in cn:
        c_start = date.fromisoformat(h["start"])
        c_end = date.fromisoformat(h["end"])
        for h_start, h_end in hk_ranges:
            overlap_start = max(c_start, h_start)
            overlap_end = min(c_end, h_end)
            if overlap_start <= overlap_end:
                # 该窗口的放假天数 = 内地放假天数
                cn_days = (c_end - c_start).days + 1
                if cn_days >= 3:
                    windows.append(
                        {
                            "festival": h["name"],
                            "cn_range": f"{c_start.isoformat()} ~ {c_end.isoformat()}",
                            "cn_days": cn_days,
                            "overlap_with_hk": f"{overlap_start.isoformat()} ~ {overlap_end.isoformat()}",
                            "hk_holidays_in_window": [
                                x["name"]
                                for x in hk
                                if overlap_start <= date.fromisoformat(x["date"]) <= overlap_end
                            ],
                        }
                    )
    # 去重（一个内地节日可能和多个香港区间重叠）
    seen: set[str] = set()
    unique: list[dict] = []
    for w in windows:
        key = w["festival"] + w["cn_range"]
        if key not in seen:
            seen.add(key)
            unique.append(w)
    return {"year": year, "windows": unique}


# ---------------------------------------------------------------------------
# 工具 4：日期计算
# ---------------------------------------------------------------------------
@tool
def days_until(target_date: str) -> dict:
    """计算从今天到目标日期还有多少天。

    Args:
        target_date: 目标日期，格式 YYYY-MM-DD，如 2026-10-01。
    """
    try:
        target = date.fromisoformat(target_date)
    except ValueError:
        return {"error": f"日期格式应为 YYYY-MM-DD，收到 {target_date!r}"}
    today = date.today()
    delta = (target - today).days
    return {
        "today": today.isoformat(),
        "target": target.isoformat(),
        "days_remaining": delta,
        "weekday_of_target": "星期" + "一二三四五六日"[target.weekday()],
    }


# ---------------------------------------------------------------------------
# 工具 5：下一个假期
# ---------------------------------------------------------------------------
@tool
def next_holiday(from_date: str = "") -> dict:
    """查询「下一个假期」：内地和香港各自最近的下一个法定假期。

    用于回答「下一个假期是什么时候」「离下个假期还有几天」这类问题。
    若 from_date 当天正处于某个假期中，也会把它作为「进行中的假期」返回。

    Args:
        from_date: 起始日期，格式 YYYY-MM-DD；缺省为今天。
    """
    if from_date:
        try:
            anchor = date.fromisoformat(from_date)
        except ValueError:
            return {"error": f"日期格式应为 YYYY-MM-DD，收到 {from_date!r}"}
    else:
        anchor = date.today()

    result: dict = {"from": anchor.isoformat(), "cn": None, "hk": None}

    # ---- 内地：假期是区间（start~end），找含 anchor 或晚于 anchor 的最近一个 ----
    cn_candidates: list[tuple[int, date, dict]] = []
    for year in available_years("cn"):
        for h in get_cn_holidays(year):
            start = date.fromisoformat(h["start"])
            end = date.fromisoformat(h["end"])
            if end >= anchor:
                cn_candidates.append(((end - anchor).days, start, h))
    if cn_candidates:
        cn_candidates.sort(key=lambda x: x[0])
        _, start, h = cn_candidates[0]
        end = date.fromisoformat(h["end"])
        result["cn"] = {
            "festival": h["name"],
            "start": h["start"],
            "end": h["end"],
            "days_until_start": (start - anchor).days,
            "in_progress": start <= anchor <= end,
            "weekday_of_start": "星期" + "一二三四五六日"[start.weekday()],
        }

    # ---- 香港：单日假期，找含 anchor 或晚于 anchor 的最近一个 ----
    hk_candidates: list[tuple[int, dict]] = []
    for year in available_years("hk"):
        for h in get_hk_holidays(year):
            d = date.fromisoformat(h["date"])
            if d >= anchor:
                hk_candidates.append(((d - anchor).days, h))
    if hk_candidates:
        hk_candidates.sort(key=lambda x: x[0])
        _, h = hk_candidates[0]
        d = date.fromisoformat(h["date"])
        result["hk"] = {
            "festival": h["name"],
            "date": h["date"],
            "days_until": (d - anchor).days,
            "in_progress": d == anchor,
            "weekday": h.get("weekday", "星期" + "一二三四五六日"[d.weekday()]),
        }

    # ---- 汇总：最早到来的那个（含进行中）----
    earliest: list[tuple[int, str]] = []
    if result["cn"]:
        earliest.append((result["cn"]["days_until_start"], "cn"))
    if result["hk"]:
        earliest.append((result["hk"]["days_until"], "hk"))
    if earliest:
        earliest.sort(key=lambda x: x[0])
        result["nearest_region"] = earliest[0][1]

    return result


# ---------------------------------------------------------------------------
# 工具 6：拼假建议
# ---------------------------------------------------------------------------
@tool
def suggest_leave_stacking(
    year: int,
    festival: str = "",
    max_leave_days: int = 3,
    region: str = "cn",
) -> dict:
    """给出节假日「拼假」建议（请假连休方案），支持内地与香港。

    拼假原理：节假日前后紧邻周末，只要请掉「假期前后的工作日」，
    就能把周末也连进来，用少量年假换超长假期。

    内地与香港差异：
      - 内地：假期多为连续多天区间，有调休补班日（拼假时需跳过）；
      - 香港：假期以单日为主（连续多日会合并），无调休，工作日=周一至五非假期。

    Args:
        year: 年份，如 2026。
        festival: 可选，只分析指定节日（如「国庆节」「圣诞节」）；
                  空字符串则分析该年所有符合条件的节日。
        max_leave_days: 最多愿意请几天假（1-5，默认 3）。
        region: "cn"（内地）或 "hk"（香港），默认 "cn"。
    """
    if not (1 <= max_leave_days <= 5):
        return {"error": "max_leave_days 必须在 1..5 之间"}
    if region not in ("cn", "hk"):
        return {"error": f"region 必须是 cn 或 hk，收到 {region!r}"}

    # ---- 区域适配：加载假期区间 ----
    if region == "cn":
        raw = get_cn_holidays(year)
        if not raw:
            return {"year": year, "note": f"暂无 {year} 年内地节假日数据", "plans": []}
        # 内地：每条记录自带 start/end 区间
        targets = []
        for h in raw:
            if festival and festival not in h["name"]:
                continue
            start = date.fromisoformat(h["start"])
            end = date.fromisoformat(h["end"])
            days = (end - start).days + 1
            if festival or days >= 3:
                targets.append((h["name"], start, end, days))
        makeup_days = {
            date.fromisoformat(d)
            for h in raw
            for d in h.get("makeup_workdays", [])
        }
    else:  # hk
        raw = get_hk_holidays(year)
        if not raw:
            return {"year": year, "note": f"暂无 {year} 年香港公众假期数据", "plans": []}
        # 香港：单日假期，先把连续日期合并成区间
        hk_dates = sorted(date.fromisoformat(h["date"]) for h in raw)
        ranges: list[tuple[date, date]] = []
        for d in hk_dates:
            if ranges and ranges[-1][1] + timedelta(days=1) >= d:
                ranges[-1] = (ranges[-1][0], d)
            else:
                ranges.append((d, d))
        targets = []
        for start, end in ranges:
            # 收集该区间内所有节日名（合并区间可能含多个节日，如年初一~年初四）
            names_in_range = [
                h["name"] for h in raw
                if start <= date.fromisoformat(h["date"]) <= end
            ]
            if festival:
                # 香港节日名是繁体（如「聖誕節」），转简体后匹配
                try:
                    from opencc import OpenCC

                    cc = OpenCC("t2s")
                    names_s = [cc.convert(n) for n in names_in_range]
                except ImportError:
                    names_s = names_in_range
                # 别名映射：用户常用说法 → 数据里的关键词
                # 如「农历新年/春节/过年」→「农历年初」
                alias_map = {
                    "农历新年": "农历年初",
                    "春节": "农历年初",
                    "过年": "农历年初",
                    "复活节": "复活节",
                    "圣诞": "圣诞",
                    "元旦": "一月一日",
                }
                keyword = alias_map.get(festival, festival)
                # 关键词命中区间内任意节日名即可（如"农历新年"匹配"农历年初一"）
                if not any(keyword in n for n in names_s):
                    continue
                name_s = "、".join(names_s)
            else:
                name_s = "、".join(names_in_range)
            days = (end - start).days + 1
            targets.append((name_s, start, end, days))
        makeup_days: set[date] = set()  # 香港无调休

    # ---- 区域适配：判断某天是否「值得请假的普通工作日」 ----
    def is_leave_candidate(d: date) -> bool:
        """判断某天是否值得请假的「工作日」。"""
        if d.weekday() >= 5:
            return False
        # 是假期 → 不用请
        for _, s, e, _ in targets:
            if s <= d <= e:
                return False
        # 是调休补班日（仅内地）→ 不算请假候选
        if d in makeup_days:
            return False
        return True

    # ---- 主逻辑：对每个请假天数生成向前/向后拼方案 ----
    plans: list[dict] = []

    def build_plan(name, start, end, holiday_days, leave_days, rest_start, rest_end):
        """构造方案。total_rest_days = 连休自然日 - 范围内实际要上班的日子。"""
        leave_set = {d.isoformat() for d in leave_days}
        work_days = 0
        d = rest_start
        while d <= rest_end:
            in_holiday = any(s <= d <= e for _, s, e, _ in targets)
            if d in makeup_days:
                work_days += 1  # 调休补班日上班
            elif d.weekday() < 5 and d.isoformat() not in leave_set and not in_holiday:
                work_days += 1  # 普通工作日（没请假）上班
            d += timedelta(days=1)
        total_rest = (rest_end - rest_start).days + 1 - work_days
        return {
            "festival": name,
            "holiday_range": f"{start.isoformat()} ~ {end.isoformat()}",
            "holiday_days": holiday_days,
            "leave_days": [d.isoformat() for d in leave_days],
            "total_rest_days": total_rest,
            "rest_range": f"{rest_start.isoformat()} ~ {rest_end.isoformat()}",
            "extra_days": total_rest - holiday_days,
        }

    for name, start, end, holiday_days in targets:
        for n_leave in range(1, max_leave_days + 1):
            # 方案 A：向后拼（rest 范围扫过周末）
            leave: list[date] = []
            cursor = end + timedelta(days=1)
            while True:
                if is_leave_candidate(cursor):
                    leave.append(cursor)
                    if len(leave) >= n_leave:
                        cursor += timedelta(days=1)
                        while not is_leave_candidate(cursor):
                            cursor += timedelta(days=1)
                        cursor -= timedelta(days=1)
                        break
                cursor += timedelta(days=1)
            plan_a = build_plan(name, start, end, holiday_days, leave, start, cursor)

            # 方案 B：向前拼（对称）
            leave_b: list[date] = []
            cursor_b = start - timedelta(days=1)
            while True:
                if is_leave_candidate(cursor_b):
                    leave_b.append(cursor_b)
                    if len(leave_b) >= n_leave:
                        cursor_b -= timedelta(days=1)
                        while not is_leave_candidate(cursor_b):
                            cursor_b -= timedelta(days=1)
                        cursor_b += timedelta(days=1)
                        break
                cursor_b -= timedelta(days=1)
            plan_b = build_plan(name, start, end, holiday_days, leave_b, cursor_b, end)

            best = max(plan_a, plan_b, key=lambda p: p["total_rest_days"])
            if best["total_rest_days"] > holiday_days:
                best["leave_count"] = n_leave
                plans.append(best)

    return {"year": year, "region": region, "max_leave_days": max_leave_days, "plans": plans}


# 导出：LangGraph 绑定用的工具列表
ALL_TOOLS = [
    get_holidays_cn,
    get_holidays_hk,
    find_common_breaks,
    days_until,
    next_holiday,
    suggest_leave_stacking,
]

# 给模型看的工具使用指引（拼进系统提示）
TOOL_GUIDE = f"""今天是 {date.today().isoformat()}。

[工具使用指引]
- 查询内地节假日 → get_holidays_cn
- 查询香港公众假期 → get_holidays_hk
- 问两地共同/接近的假期 → find_common_breaks
- 算距离某日期还有几天 → days_until
- 问「下一个假期是什么/还有几天」（内地+香港各自最近的一个）→ next_holiday
- 问「怎么请假连休/拼假最划算」（内地或香港）→ suggest_leave_stacking
  参数 region="cn" 或 "hk"，默认 "cn"
- 数据覆盖：内地 2025-2026，香港 2025-2027。
"""
