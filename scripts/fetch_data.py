"""抓取官方节假日数据 → 生成本地 JSON。

数据源（官方权威）：
  - 香港公众假期：GovHK 各年页面（表格结构）
      https://www.gov.hk/tc/about/abouthk/holiday/{year}.htm
  - 内地节假日：国务院办公厅放假安排通知（正文段落结构）
      2025: https://www.gov.cn/zhengce/zhengceku/202411/content_6986383.htm
      2026: https://www.gov.cn/zhengce/content/202511/content_7047090.htm

用法：
  python scripts/fetch_data.py            # 抓取所有配置的年份
  python scripts/fetch_data.py --region hk --years 2027
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# ---------------------------------------------------------------------------
# 配置：每个来源的年份 → URL
# ---------------------------------------------------------------------------
HK_URLS = {year: f"https://www.gov.hk/tc/about/abouthk/holiday/{year}.htm" for year in (2025, 2026, 2027)}

CN_URLS = {
    2025: "https://www.gov.cn/zhengce/zhengceku/202411/content_6986383.htm",
    2026: "https://www.gov.cn/zhengce/content/202511/content_7047090.htm",
    # 2027 年内地安排尚未发布（通常前一年 10-11 月公布），届时补充
}


def fetch(url: str) -> str:
    """抓取页面，返回 HTML 文本。"""
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    # gov.cn 页面是 utf-8；gov.hk 页面带 BOM，统一解码
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


# ---------------------------------------------------------------------------
# 香港：解析 GovHK 表格（<tr> 行：节日名 | 日期 | 星期）
# ---------------------------------------------------------------------------
def parse_hk(html_text: str, year: int) -> list[dict]:
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, re.S)
    holidays: list[dict] = []
    for row in rows:
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        cells = [c.replace("\xa0", " ").strip() for c in cells if c.strip()]
        # 期望三列：名称 | 日期（如 1月1日）| 星期
        if len(cells) < 2:
            continue
        name = cells[0]
        date_str = cells[1]
        m = re.match(r"(\d{1,2})月(\d{1,2})日", date_str)
        if not m:
            continue
        month, day = int(m.group(1)), int(m.group(2))
        holidays.append(
            {
                "name": name,
                "date": f"{year}-{month:02d}-{day:02d}",
                "weekday": cells[2] if len(cells) > 2 else "",
            }
        )
    return holidays


# ---------------------------------------------------------------------------
# 内地：解析国务院通知正文（<p><strong>节日：</strong>安排</p>）
# ---------------------------------------------------------------------------
def parse_cn(html_text: str, year: int) -> list[dict]:
    # 先去掉 script/style，再取 <p> 段落
    text = re.sub(r"<script.*?</script>", "", html_text, flags=re.S)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S)
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", text, re.S)

    holidays: list[dict] = []
    for p in paragraphs:
        plain = re.sub(r"<[^>]+>", "", p).strip()
        # 匹配形如：一、元旦：1月1日（周三）放假1天，不调休。
        m = re.match(r"^[一二三四五六七八九十]+、(.+?)[：:]\s*(.+)$", plain)
        if not m:
            continue
        name = m.group(1).strip()
        detail = m.group(2).strip()
        # 提取放假区间：X月X日（周X）至X月X日（周X），或单日 X月X日（周X）放假
        # 注意：detail 中"上班"的日期（调休）不属于放假区间，需排除
        # 先找"至"前的主区间：取第一个日期 和 "至" 后的第一个日期
        dates = re.findall(r"(\d{1,2})月(\d{1,2})日", detail)
        if not dates:
            continue
        first = (int(dates[0][0]), int(dates[0][1]))
        # 找到放假结束日：取"至"后的日期（原文常省略月份，如"至3日"）；
        # 若无"至"则单日放假
        last = first
        m_to = re.search(r"至\s*(?:(\d{1,2})月)?(\d{1,2})日", detail)
        if m_to:
            last_month = int(m_to.group(1)) if m_to.group(1) else first[0]
            last = (last_month, int(m_to.group(2)))
        # 找出调休上班日（如"2月14日（周六）、2月28日（周六）上班"）
        # 注意：多个补班日用顿号连接，第一个日期后面可能不直接跟"上班"，
        # 所以取"上班"所在句子的整体片段，提取其中所有日期
        workdays: list[str] = []
        for seg in re.findall(r"[^。；]*上班", detail):
            for (m2, d2) in re.findall(r"(\d{1,2})月(\d{1,2})日", seg):
                workdays.append(f"{year}-{int(m2):02d}-{int(d2):02d}")
        holidays.append(
            {
                "name": name,
                "start": f"{year}-{first[0]:02d}-{first[1]:02d}",
                "end": f"{year}-{last[0]:02d}-{last[1]:02d}",
                "detail": detail,
                "makeup_workdays": workdays,
            }
        )
    return holidays


# ---------------------------------------------------------------------------
# 统一输出
# ---------------------------------------------------------------------------
PARSERS = {"hk": parse_hk, "cn": parse_cn}
URLS = {"hk": HK_URLS, "cn": CN_URLS}
OUT_NAMES = {"hk": "holidays_hk_{year}.json", "cn": "holidays_cn_{year}.json"}


def run(region: str, years: list[int]) -> None:
    if region not in PARSERS:
        sys.exit(f"未知 region: {region}（可选 hk / cn）")
    parser = PARSERS[region]
    urls = URLS[region]
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for year in years:
        if year not in urls:
            print(f"[skip] {region} {year}: 未配置 URL")
            continue
        print(f"[fetch] {region} {year}: {urls[year]}")
        html_text = fetch(urls[year])
        data = parser(html_text, year)
        out = DATA_DIR / OUT_NAMES[region].format(year=year)
        out.write_text(json.dumps({"year": year, "region": region, "holidays": data}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[save] {out} ({len(data)} 条)")


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取官方节假日数据 → 本地 JSON")
    parser.add_argument("--region", choices=["hk", "cn", "all"], default="all")
    parser.add_argument("--years", nargs="+", type=int, default=None, help="年份列表，缺省用配置的全部")
    args = parser.parse_args()

    regions = ["hk", "cn"] if args.region == "all" else [args.region]
    for region in regions:
        years = args.years or sorted(URLS[region].keys())
        run(region, years)


if __name__ == "__main__":
    main()
