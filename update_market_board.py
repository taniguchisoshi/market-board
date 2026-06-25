#!/usr/bin/env python3
"""Update the market board news block with five Japanese news items."""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin
from zoneinfo import ZoneInfo

import feedparser
import requests
from openai import OpenAI


AUTO_NEWS_START = "<!-- AUTO_NEWS_START -->"
AUTO_NEWS_END = "<!-- AUTO_NEWS_END -->"

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
JST = ZoneInfo("Asia/Tokyo")

JAPANESE_QUERIES = [
    "ブルームバーグ 米国株 マーケット 日本語",
    "Bloomberg 米国株 日本語 S&P500 ナスダック",
    "米国株 株価 日本語",
    "NYダウ ナスダック S&P500 日本語",
    "FRB FOMC 金利 米国株 日本語",
    "米国 決算 株価 日本語",
    "エヌビディア 半導体 米国株 日本語",
    "米国 景気指標 株式市場 日本語",
    "原油 金利 為替 米国株 日本語",
]

ENGLISH_FALLBACK_QUERIES = [
    "US stocks market moving news",
    "Federal Reserve Treasury yields Nasdaq stocks",
    "Nvidia Magnificent Seven earnings stocks",
]


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    source: str
    published: str
    language: str
    summary: str


def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def google_news_rss_url(query: str, *, japanese: bool) -> str:
    if japanese:
        return (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(query + ' when:1d')}&hl=ja&gl=JP&ceid=JP:ja"
        )
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query + ' when:1d')}&hl=en-US&gl=US&ceid=US:en"
    )


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_title(title: str) -> str:
    title = re.sub(r"\s+", "", title.lower())
    return re.sub(r"[|｜:：\-ー–—].*$", "", title)


def fetch_news_candidates(max_articles: int = 40) -> list[Article]:
    articles: list[Article] = []
    seen: set[str] = set()

    def collect(query: str, *, japanese: bool) -> None:
        nonlocal articles
        feed = feedparser.parse(google_news_rss_url(query, japanese=japanese))
        for entry in feed.entries:
            title = clean_text(getattr(entry, "title", ""))
            url = getattr(entry, "link", "")
            if not title or not url:
                continue

            key = normalize_title(title)
            if key in seen:
                continue
            seen.add(key)

            source = ""
            if hasattr(entry, "source"):
                source = clean_text(getattr(entry.source, "title", ""))

            articles.append(
                Article(
                    title=title,
                    url=url,
                    source=source or "Google News",
                    published=clean_text(getattr(entry, "published", "")),
                    language="ja" if japanese else "en",
                    summary=clean_text(getattr(entry, "summary", "")),
                )
            )

    for query in JAPANESE_QUERIES:
        collect(query, japanese=True)
        if len(articles) >= max_articles:
            break

    if len(articles) < 15:
        for query in ENGLISH_FALLBACK_QUERIES:
            collect(query, japanese=False)
            if len(articles) >= max_articles:
                break

    return articles[:max_articles]


def summarize_with_openai(articles: list[Article]) -> list[dict[str, str]]:
    if not articles:
        raise RuntimeError("No news candidates were found.")

    client = OpenAI(api_key=env_required("OPENAI_API_KEY"))
    today_jst = datetime.now(JST).strftime("%Y-%m-%d")
    candidate_payload = [
        {
            "title": article.title,
            "url": article.url,
            "source": article.source,
            "published": article.published,
            "language": article.language,
            "summary": article.summary,
        }
        for article in articles
    ]

    system_prompt = (
        "あなたは米国株の朝ライブ用ニュース編集者です。"
        "日本語記事を最優先し、米国株の値動きに関係する材料を5本だけ選びます。"
        "考察、投資判断、ライブ用コメントは入れず、事実関係だけを短く要約してください。"
    )
    user_prompt = f"""
今日の日付: {today_jst}

候補記事JSON:
{json.dumps(candidate_payload, ensure_ascii=False)}

必ず次のJSON形式だけで返してください。
{{
  "items": [
    {{
      "headline": "見出し",
      "summary": "記事内容の要約。120字以内。事実だけを書く",
      "url": "記事URL"
    }}
  ]
}}

条件:
- itemsは必ず5本。
- 上から米国株へのインパクトが大きい順に並べる。
- headlineは短くキャッチーな見出しにする。
- summaryは記事の要約だけにする。相場への見方、投資判断、ライブで話す一言、確認ポイントは書かない。
- 日本語記事リンクを優先。
- 日本語記事が十分でない場合は、Bloombergなど市場系メディアの見出しを参考に重要ニュースを補う。
- 米国株の指数、金利、FRB、為替、原油、半導体、大型テック、決算に関係が薄い記事は選ばない。
- PMI、CPI、PCE、雇用統計などの経済指標は、今日発表されたものだけを選ぶ。発表待ちや古い指標をニュース扱いしない。
- 同じテーマの重複を避ける。
- URLは候補記事に含まれるものだけを使う。
- ソース確認状況に関する注意書きや補足ラベルは出力しない。
"""

    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)
    items = parsed.get("items", [])
    if not isinstance(items, list) or len(items) != 5:
        raise RuntimeError(f"OpenAI response did not contain exactly 5 items: {content}")

    required = {"headline", "summary", "url"}
    for item in items:
        if not isinstance(item, dict) or not required.issubset(item):
            raise RuntimeError(f"OpenAI response item is missing required fields: {item}")
    return items


def render_news_html(items: list[dict[str, str]]) -> str:
    generated_at = datetime.now(timezone.utc).astimezone(JST).strftime("%Y-%m-%d %H:%M %Z")
    blocks = [
        '<div style="display:flex;flex-direction:column;gap:14px;">',
        (
            '  <div style="margin:0 0 2px;color:#d6deee;font-size:14px;font-weight:800;line-height:1.6;">'
            f"最終更新: {html.escape(generated_at)}</div>"
        ),
    ]

    for item in items:
        blocks.extend(
            [
                '  <article style="background:#16233c;border:1px solid #3b4a66;border-radius:18px;padding:20px 22px;box-sizing:border-box;">',
                (
                    '    <h3 style="margin:0 0 10px;color:#ffffff;font-size:23px;line-height:1.35;font-weight:900;">'
                    f"{html.escape(item['headline'])}</h3>"
                ),
                (
                    '    <p style="margin:0 0 10px;color:#d6deee;font-size:16px;font-weight:750;line-height:1.85;">'
                    f"{html.escape(item['summary'])}</p>"
                ),
                (
                    '    <a href="'
                    + html.escape(item["url"], quote=True)
                    + '" target="_blank" rel="noopener noreferrer" '
                    + 'style="display:inline-block;margin-top:4px;color:#7dd3fc;font-size:15px;font-weight:900;text-decoration:underline;">ソースリンク</a>'
                ),
                "  </article>",
            ]
        )

    blocks.extend(["</div>"])
    return "\n".join(line for line in blocks if line)


def auth_headers(username: str, app_password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{app_password}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "User-Agent": "market-board-updater/1.0",
    }


def wordpress_api_url(base_url: str, page_id: str) -> str:
    base = base_url.rstrip("/") + "/"
    return urljoin(base, f"wp-json/wp/v2/pages/{page_id}")


def get_wordpress_page() -> tuple[str, dict[str, str], dict[str, Any]]:
    url = wordpress_api_url(env_required("WORDPRESS_URL"), env_required("WORDPRESS_PAGE_ID"))
    headers = auth_headers(
        env_required("WORDPRESS_USERNAME"),
        env_required("WORDPRESS_APP_PASSWORD"),
    )
    response = requests.get(
        url,
        params={"context": "edit"},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return url, headers, response.json()


def page_content(page: dict[str, Any]) -> str:
    content = page.get("content", {})
    if isinstance(content, dict):
        raw = content.get("raw")
        if raw:
            return raw
        rendered = content.get("rendered")
        if rendered:
            return rendered
    raise RuntimeError("Could not read WordPress page content.")


def replace_auto_news_block(content: str, news_html: str) -> str:
    start = content.find(AUTO_NEWS_START)
    end = content.find(AUTO_NEWS_END)
    if start == -1 or end == -1 or start >= end:
        raise RuntimeError(
            "AUTO_NEWS markers were not found in the WordPress page. "
            "Add the starter HTML from README.md first."
        )

    before = content[: start + len(AUTO_NEWS_START)]
    after = content[end:]
    return f"{before}\n{news_html}\n{after}"


def update_wordpress_page(new_content: str) -> None:
    url, headers, _ = get_wordpress_page()
    payload: dict[str, Any] = {"content": new_content}

    response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
    response.raise_for_status()


def build_news_html() -> str:
    articles = fetch_news_candidates()
    items = summarize_with_openai(articles)
    return render_news_html(items)


def update_html_file(path: Path, news_html: str) -> bool:
    current_content = path.read_text(encoding="utf-8")
    new_content = replace_auto_news_block(current_content, news_html)
    if new_content == current_content:
        return False
    path.write_text(new_content, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Update market board news block.")
    parser.add_argument(
        "--html-file",
        help="Update a local HTML file, such as index.html, instead of WordPress.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build HTML but do not update WordPress.")
    parser.add_argument("--print-html", action="store_true", help="Print generated HTML.")
    args = parser.parse_args()

    news_html = build_news_html()
    if args.print_html:
        print(news_html)

    if args.html_file:
        html_file = Path(args.html_file)
        if args.dry_run:
            current_content = html_file.read_text(encoding="utf-8")
            replace_auto_news_block(current_content, news_html)
            print(f"Dry run OK: {html_file}")
            return 0

        changed = update_html_file(html_file, news_html)
        if changed:
            print(f"Updated HTML file: {html_file}")
        else:
            print(f"No change needed: {html_file}")
        return 0

    if args.dry_run:
        return 0

    _, _, page = get_wordpress_page()
    current_content = page_content(page)
    new_content = replace_auto_news_block(current_content, news_html)
    update_wordpress_page(new_content)
    print("Updated WordPress market board news block.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
