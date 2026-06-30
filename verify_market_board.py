#!/usr/bin/env python3
"""Verify the market board HTML before and after GitHub Pages publication."""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
JP_WEEKDAYS = "月火水木金土日"


def expected_dates() -> tuple[str, str]:
    now = datetime.now(timezone.utc).astimezone(JST)
    iso = now.strftime("%Y-%m-%d")
    jp = f"{now.year}年{now.month}月{now.day}日（{JP_WEEKDAYS[now.weekday()]}）"
    return iso, jp


def read_public_url(url: str) -> str:
    separator = "&" if "?" in url else "?"
    cache_busted_url = f"{url}{separator}v={int(time.time())}"
    request = Request(
        cache_busted_url,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "market-board-verifier/1.0",
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def check_html(html: str) -> list[str]:
    expected_iso, expected_jp = expected_dates()
    failures: list[str] = []

    try:
        block = html[html.index("<!-- AUTO_NEWS_START -->") : html.index("<!-- AUTO_NEWS_END -->")]
    except ValueError:
        return ["AUTO_NEWS markers are missing."]

    try:
        index_chart = html[html.index('<section id="mb-chart-index"') : html.index('<section id="mb-chart-heatmap"')]
    except ValueError:
        index_chart = ""
        failures.append("Index chart section is missing.")

    header_match = re.search(
        r'<p style="margin:0 0 10px;color:#7dd3fc;font-size:18px;font-weight:900;">([^<]+)</p>',
        html,
    )
    if not header_match or header_match.group(1) != expected_jp:
        failures.append(f"Top-left date is not today's JST date: expected {expected_jp}.")

    if f"翌営業日チェック：{expected_jp}" not in html:
        failures.append(f"Next-session check date is not today's JST date: expected {expected_jp}.")

    updated_match = re.search(r"最終更新:\s*([^<]+)", block)
    if not updated_match or expected_iso not in updated_match.group(1) or "JST" not in updated_match.group(1):
        failures.append(f"News updated timestamp is not today's JST date: expected {expected_iso} JST.")

    checks = {
        "five news source links": len(re.findall(r'href="#mb-news-[1-5]"', block)) == 5,
        "five news popups": len(re.findall(r'<section id="mb-news-[1-5]" class="market-board-popup">', block)) == 5,
        "five source buttons": block.count("ソース記事を開く") == 5,
        "no iframe": "<iframe" not in html,
        "no Google Finance": "google.com/finance" not in html,
        "ten Yahoo Finance SVG charts": html.count("Yahoo Financeの価格データから生成した画像です") == 10,
        "index chart uses indexes": all(x in index_chart for x in ["NASDAQ100", "S&amp;P500", "DOW", "Russell2000"]),
        "index chart excludes ETFs": all(x not in index_chart for x in ["QQQ", "SPY", "DIA", "IWM"]),
        "previous close baseline": "前日終値 = 0%" in html,
        "USD/JPY shows decimal price": bool(re.search(r"USD/JPY\s+\d{1,3}\.\d{3}円\s+/\s+[+-]\d+\.\d{2}%", html)),
    }
    failures.extend(name for name, passed in checks.items() if not passed)

    for chart_id in re.findall(r'<section id="(mb-chart-[^"]+)" class="market-board-popup">', html):
        if chart_id == "mb-chart-heatmap":
            continue
        section = html[html.index(f'<section id="{chart_id}"') :]
        section = section[: section.index("</section>")]
        label_ys = [
            float(y_value) + 14
            for y_value in re.findall(r'<rect x="920" y="([0-9.]+)" width="154" height="27"', section)
        ]
        if not label_ys:
            failures.append(f"{chart_id} has no visible right-edge percent labels.")
            continue
        gaps = [b - a for a, b in zip(sorted(label_ys), sorted(label_ys)[1:])]
        if any(gap < 33.9 for gap in gaps):
            failures.append(f"{chart_id} right-edge percent labels overlap.")
        chip_pct_count = len(re.findall(r"/\s*[+-]\d+\.\d{2}%</text>", section))
        if chip_pct_count < len(label_ys):
            failures.append(f"{chart_id} price chips do not all include percent values.")
    return failures


def verify_text(html: str, label: str) -> bool:
    failures = check_html(html)
    if not failures:
        print(f"OK: {label}")
        return True
    print(f"FAILED: {label}", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify market board HTML.")
    parser.add_argument("--html-file", default="index.html")
    parser.add_argument("--public-url")
    parser.add_argument("--wait-public-seconds", type=int, default=0)
    args = parser.parse_args()

    html = Path(args.html_file).read_text(encoding="utf-8")
    if not verify_text(html, args.html_file):
        return 1

    if not args.public_url:
        return 0

    deadline = time.time() + args.wait_public_seconds
    while True:
        try:
            if verify_text(read_public_url(args.public_url), args.public_url):
                return 0
        except Exception as exc:
            print(f"FAILED: {args.public_url}: {exc}", file=sys.stderr)
        if time.time() >= deadline:
            return 1
        time.sleep(15)


if __name__ == "__main__":
    raise SystemExit(main())
