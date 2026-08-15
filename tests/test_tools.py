"""工具层测试：验证 6 个工具的关键行为。

重点覆盖拼假逻辑——这是我们反复调过的复杂逻辑，
必须有测试保护，防止以后改代码时弄坏。
"""
from __future__ import annotations

from trip_pal.tools import (
    days_until,
    find_common_breaks,
    get_holidays_cn,
    get_holidays_hk,
    next_holiday,
    suggest_leave_stacking,
)


class TestHolidayTools:
    def test_get_holidays_cn_oct_2026(self):
        """2026 年 10 月内地应只有国庆节 1 个节日。"""
        r = get_holidays_cn.invoke({"year": 2026, "month": 10})
        assert len(r["holidays"]) == 1
        assert r["holidays"][0]["name"] == "国庆节"

    def test_get_holidays_cn_2027_empty(self):
        """2027 内地数据尚未发布，应返回空并带说明。"""
        r = get_holidays_cn.invoke({"year": 2027})
        assert r["holidays"] == []
        assert "note" in r

    def test_get_holidays_hk_feb_2027(self):
        """2027 年 2 月香港应有农历新年假期（年初一/三/四）。"""
        r = get_holidays_hk.invoke({"year": 2027, "month": 2})
        names = [h["name"] for h in r["holidays"]]
        assert any("年初" in n for n in names), f"2月应含农历新年假期: {names}"

    def test_days_until(self):
        """days_until 应正确计算天数。"""
        r = days_until.invoke({"target_date": "2026-10-01"})
        assert r["days_remaining"] > 0
        assert r["weekday_of_target"] == "星期四"


class TestNextHoliday:
    """下一个假期工具测试。"""

    def test_from_mid_august_2026(self):
        """2026-08-15 起：内地下一个应是中秋节（9/25），香港最近是中秋翌日（9/26）。"""
        r = next_holiday.invoke({"from_date": "2026-08-15"})
        assert r["cn"]["festival"] == "中秋节"
        assert r["cn"]["days_until_start"] == 41  # 9/25 - 8/15
        assert r["hk"]["festival"] == "中秋節翌日"
        assert r["hk"]["days_until"] == 42  # 9/26 - 8/15
        assert r["nearest_region"] == "cn"

    def test_from_inside_holiday_marks_in_progress(self):
        """2026-10-03（国庆假期中）应标记 in_progress=True。"""
        r = next_holiday.invoke({"from_date": "2026-10-03"})
        assert r["cn"]["festival"] == "国庆节"
        assert r["cn"]["in_progress"] is True
        assert r["cn"]["days_until_start"] == -2

    def test_from_late_2026_no_cn_data(self):
        """2026-12-15 起：内地无 2027 数据 → cn 为 None，香港还有圣诞（繁体名）。"""
        r = next_holiday.invoke({"from_date": "2026-12-15"})
        assert r["cn"] is None
        assert r["hk"] is not None
        assert r["hk"]["festival"] == "聖誕節"
        assert r["nearest_region"] == "hk"

    def test_invalid_date(self):
        """非法日期应返回 error。"""
        r = next_holiday.invoke({"from_date": "not-a-date"})
        assert "error" in r


class TestFindCommonBreaks:
    def test_2026_has_common_windows(self):
        """2026 内地长假应都能和香港找到重叠窗口。"""
        r = find_common_breaks.invoke({"year": 2026})
        assert len(r["windows"]) >= 5, f"应有多个共同假期窗口: {r}"


class TestLeaveStacking:
    """拼假逻辑测试（重点保护，防止回归）。"""

    def test_cn_national_day_2_days(self):
        """2026 国庆请 2 天（10/8、10/9）→ 应休 10 天（跳过 10/10 补班）。"""
        r = suggest_leave_stacking.invoke(
            {"year": 2026, "festival": "国庆节", "max_leave_days": 2, "region": "cn"}
        )
        plan_2 = next(p for p in r["plans"] if p["leave_count"] == 2)
        assert plan_2["leave_days"] == ["2026-10-08", "2026-10-09"]
        assert plan_2["total_rest_days"] == 10, f"应休10天，实际 {plan_2}"

    def test_cn_national_day_does_not_include_makeup_day(self):
        """拼假不应把调休补班日（10/10）算作请假候选。"""
        r = suggest_leave_stacking.invoke(
            {"year": 2026, "festival": "国庆节", "max_leave_days": 3, "region": "cn"}
        )
        for p in r["plans"]:
            assert "2026-10-10" not in p["leave_days"], f"补班日不该被请: {p}"

    def test_hk_christmas_1_day(self):
        """香港 2026 圣诞请 1 天（12/28）→ 应休 4 天。"""
        r = suggest_leave_stacking.invoke(
            {"year": 2026, "festival": "圣诞节", "max_leave_days": 1, "region": "hk"}
        )
        assert len(r["plans"]) == 1
        p = r["plans"][0]
        assert p["leave_days"] == ["2026-12-28"]
        assert p["total_rest_days"] == 4, f"应休4天，实际 {p}"

    def test_hk_lunar_new_year_alias(self):
        """香港「农历新年/春节」别名应能匹配到农历年初假期。"""
        r = suggest_leave_stacking.invoke(
            {"year": 2026, "festival": "春节", "max_leave_days": 1, "region": "hk"}
        )
        assert len(r["plans"]) >= 1, "春节别名应匹配到方案"
