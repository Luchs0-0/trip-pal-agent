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
# 工具 5：拼假建议
# ---------------------------------------------------------------------------
@tool
def suggest_leave_stacking(
    year: int,
    festival: str = "",
    max_leave_days: int = 3,
) -> dict:
    """给出内地节假日的「拼假」建议（请假连休方案）。

    拼假原理：节假日前后紧邻周末/调休，只要请掉「假期前后的工作日」，
    就能把周末也连进来，用少量年假换超长假期。

    Args:
        year: 年份，如 2026。
        festival: 可选，只分析指定节日（如「国庆节」「劳动节」）；
                  空字符串则分析该年所有 ≥3 天的节日。
        max_leave_days: 最多愿意请几天假（1-5，默认 3）。
    """
    if not (1 <= max_leave_days <= 5):
        return {"error": "max_leave_days 必须在 1..5 之间"}

    holidays = get_cn_holidays(year)
    if not holidays:
        return {"year": year, "note": f"暂无 {year} 年内地节假日数据", "plans": []}

    # 过滤：指定节日，或 ≥3 天的长假
    targets = []
    for h in holidays:
        if festival and festival not in h["name"]:
            continue
        start = date.fromisoformat(h["start"])
        end = date.fromisoformat(h["end"])
        days = (end - start).days + 1
        if festival or days >= 3:
            targets.append((h["name"], start, end, days))

    plans: list[dict] = []

    def build_plan(name, start, end, holiday_days, leave_days, rest_start, rest_end):
        """构造一个方案 dict。

        total_rest_days = 连休范围内的自然日 - 范围内「实际要上班」的日子。
        要上班的日子 = 普通工作日中没请假的 + 调休补班日。
        这样才算「真正能休息的天数」。
        """
        leave_set = {d.isoformat() for d in leave_days}
        work_days = 0
        d = rest_start
        while d <= rest_end:
            # 调休补班日 → 上班
            for h in get_cn_holidays(year):
                if d.isoformat() in h.get("makeup_workdays", []):
                    work_days += 1
                    break
            else:
                # 普通工作日（周一至五、非节假日、非请假）→ 上班
                if d.weekday() < 5 and d.isoformat() not in leave_set:
                    in_holiday = any(
                        date.fromisoformat(h["start"]) <= d <= date.fromisoformat(h["end"])
                        for h in get_cn_holidays(year)
                    )
                    if not in_holiday:
                        work_days += 1
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
        # ---- 拼假核心逻辑 ----
        # 注意：拼假时「调休上班日」（如国庆后的周六补班）不算请假候选——
        # 因为补班日本来就要上班，请它只换 1 天，不划算；
        # 真正划算的是请「普通工作日」（周一至五且非节假日），
        # 它能连上后面的周末，用 1 天年假换 2-3 天休息。
        def is_leave_candidate(d: date) -> bool:
            """判断某天是否值得请假的「普通工作日」。"""
            # 周一至五
            if d.weekday() >= 5:
                return False
            # 是节假日 → 不用请
            for h in get_cn_holidays(year):
                hs, he = date.fromisoformat(h["start"]), date.fromisoformat(h["end"])
                if hs <= d <= he:
                    return False
            # 是调休上班日（周末补班）→ 不算请假候选（见上注释）
            for h in get_cn_holidays(year):
                if d.isoformat() in h.get("makeup_workdays", []):
                    return False
            return True

        # 对每个请假天数（1..max_leave_days）生成方案，让用户权衡
        for n_leave in range(1, max_leave_days + 1):
            # 方案 A：向后拼。注意 rest 范围要「扫过周末」——
            # 请满 n 天后，还要继续扫到下一个「可请日」才停，
            # 这样中间的周末/补班日都算进连休范围。
            leave: list[date] = []
            cursor = end + timedelta(days=1)
            while True:
                if is_leave_candidate(cursor):
                    leave.append(cursor)
                    if len(leave) >= n_leave:
                        # 已请满：继续往后扫，直到下一个可请日（边界）
                        cursor += timedelta(days=1)
                        while not is_leave_candidate(cursor):
                            cursor += timedelta(days=1)
                        cursor -= timedelta(days=1)  # 边界的前一天 = 连休最后一天
                        break
                cursor += timedelta(days=1)
            plan_a = build_plan(name, start, end, holiday_days, leave, start, cursor)

            # 方案 B：向前拼（对称逻辑）
            leave_b: list[date] = []
            cursor_b = start - timedelta(days=1)
            while True:
                if is_leave_candidate(cursor_b):
                    leave_b.append(cursor_b)
                    if len(leave_b) >= n_leave:
                        cursor_b -= timedelta(days=1)
                        while not is_leave_candidate(cursor_b):
                            cursor_b -= timedelta(days=1)
                        cursor_b += timedelta(days=1)  # 边界后一天 = 连休第一天
                        break
                cursor_b -= timedelta(days=1)
            plan_b = build_plan(name, start, end, holiday_days, leave_b, cursor_b, end)

            best = max(plan_a, plan_b, key=lambda p: p["total_rest_days"])
            # 该方案比上一档更优才保留（避免冗余）
            if best["total_rest_days"] > holiday_days:
                best["leave_count"] = n_leave
                plans.append(best)

    return {"year": year, "max_leave_days": max_leave_days, "plans": plans}


# 导出：LangGraph 绑定用的工具列表
ALL_TOOLS = [get_holidays_cn, get_holidays_hk, find_common_breaks, days_until, suggest_leave_stacking]

# 给模型看的工具使用指引（拼进系统提示）
TOOL_GUIDE = f"""今天是 {date.today().isoformat()}。

[工具使用指引]
- 查询内地节假日 → get_holidays_cn
- 查询香港公众假期 → get_holidays_hk
- 问两地共同/接近的假期 → find_common_breaks
- 算距离某日期还有几天 → days_until
- 问「怎么请假连休/拼假最划算」→ suggest_leave_stacking
- 数据覆盖：内地 2025-2026，香港 2025-2027。
"""
