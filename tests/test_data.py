"""数据层测试：验证官方数据文件完整、可加载。

这些测试不依赖 LLM / 网络，只读本地 JSON，跑得快且稳定。
"""
from __future__ import annotations

from trip_pal.data_loader import available_years, get_cn_holidays, get_hk_holidays


class TestDataLoader:
    def test_hk_data_available(self):
        """香港数据应覆盖 2025-2027 三年。"""
        years = available_years("hk")
        assert 2025 in years
        assert 2026 in years
        assert 2027 in years

    def test_cn_data_available(self):
        """内地数据应覆盖 2025-2026（2027 待官方发布）。"""
        years = available_years("cn")
        assert 2025 in years
        assert 2026 in years

    def test_hk_2027_has_data(self):
        """香港 2027 应有公众假期数据（每年约 17 天）。"""
        holidays = get_hk_holidays(2027)
        assert len(holidays) >= 15, f"香港 2027 数据异常：{len(holidays)} 条"

    def test_cn_2026_has_all_festivals(self):
        """内地 2026 应有 7 个主要节日（元旦/春节/清明/劳动/端午/中秋/国庆）。"""
        holidays = get_cn_holidays(2026)
        names = [h["name"] for h in holidays]
        for expected in ["元旦", "春节", "清明节", "劳动节", "端午节", "中秋节", "国庆节"]:
            assert expected in names, f"缺少节日: {expected}"

    def test_cn_2026_spring_festival_makeup_days(self):
        """2026 春节应有 2 个调休上班日（2/14、2/28）。"""
        holidays = get_cn_holidays(2026)
        chunjie = next(h for h in holidays if h["name"] == "春节")
        assert "2026-02-14" in chunjie["makeup_workdays"]
        assert "2026-02-28" in chunjie["makeup_workdays"]
