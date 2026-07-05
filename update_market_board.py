#!/usr/bin/env python3
"""Update the market board news block with five Japanese news items.

This free version does not call the OpenAI API. It scores Japanese news from
Google News RSS and formats the top five market-moving items for the board.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlencode, urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


AUTO_NEWS_START = "<!-- AUTO_NEWS_START -->"
AUTO_NEWS_END = "<!-- AUTO_NEWS_END -->"

JST = ZoneInfo("Asia/Tokyo")
JP_WEEKDAYS = "月火水木金土日"

BLOOMBERG_QUERIES = [
    '"米国市況" Bloomberg',
    '"米国市況" ブルームバーグ',
    '"S&P500" "Bloomberg" "米国市況"',
    '"米国株" "Bloomberg" "S&P500"',
    '"ナスダック" "Bloomberg" "米国市況"',
    '"マイクロン" "Bloomberg" "米国株"',
    '"円" "40年ぶり" "Bloomberg"',
    '"為替" "Bloomberg" "円" "安値"',
    '"ドル円" "Bloomberg" "円"',
    '"停戦合意" "Bloomberg"',
    '"停戦" "合意" "Bloomberg" "市場"',
    '"中東" "停戦" "原油" "Bloomberg"',
    '"イスラエル" "イラン" "停戦" "Bloomberg"',
]

JAPANESE_QUERIES = [
    *BLOOMBERG_QUERIES,
    "米国株 株価 日本語",
    "NYダウ ナスダック S&P500 日本語",
    "FRB FOMC 金利 米国株 日本語",
    "米国 決算 株価 日本語",
    "エヌビディア 半導体 米国株 日本語",
    "米国 景気指標 株式市場 日本語",
    "原油 金利 為替 米国株 日本語",
]

IMPACT_KEYWORDS = {
    "米国株": 12,
    "米株": 12,
    "Ｓ＆Ｐ５００": 12,
    "S&P500": 12,
    "ナスダック": 12,
    "NASDAQ": 12,
    "NYダウ": 10,
    "ダウ": 8,
    "FRB": 12,
    "FOMC": 12,
    "金利": 11,
    "利下げ": 11,
    "利上げ": 11,
    "米国債": 10,
    "長期金利": 10,
    "CPI": 10,
    "PCE": 10,
    "雇用統計": 10,
    "PMI": 8,
    "GDP": 8,
    "決算": 9,
    "エヌビディア": 11,
    "NVIDIA": 11,
    "半導体": 10,
    "AI半導体": 9,
    "アップル": 8,
    "Apple": 8,
    "マイクロソフト": 8,
    "Microsoft": 8,
    "アルファベット": 8,
    "Google": 8,
    "アマゾン": 8,
    "Amazon": 8,
    "メタ": 8,
    "Meta": 8,
    "テスラ": 8,
    "Tesla": 8,
    "原油": 9,
    "ドル円": 9,
    "為替": 8,
    "40年ぶり": 12,
    "対ドル": 9,
    "円安": 9,
    "円高": 8,
    "介入": 8,
    "中東": 7,
    "停戦": 18,
    "停戦合意": 28,
    "ホルムズ": 11,
    "イラン": 9,
    "イスラエル": 9,
    "報復": 8,
    "攻撃応酬": 12,
    "協議再開": 10,
    "関税": 7,
}

EXCLUDED_SOURCES = {
    "Moomoo",
}

SOURCE_BONUS = {
    "Bloomberg": 45,
    "Bloomberg.com": 50,
    "ブルームバーグ": 45,
    "TBS NEWS DIG": 38,
    "Yahoo!ファイナンス": 30,
    "ロイター": 12,
    "Reuters": 12,
    "日本経済新聞": 10,
    "日経": 10,
    "NHK": 7,
    "Yahoo": 4,
}

EXCLUDE_NEWS_PATTERNS = re.compile(
    r"\bQuote\b|Stock Price Quote|Fund\s+-\s+Bloomberg|Analysis\s+-|"
    r"Index\s+-\s+Bloomberg|^\w{2,10}[:：]\s|"
    r"ファンド|投信|投資信託|基準価額|eMAXIS|Slim米国株式|\b\d{8}\b|"
    r"株価・株式情報|株価情報|株式情報|指数情報・推移|【[A-Z0-9=.^-]{1,12}】|"
    r"為替レート・相場|指数情報・推移|決算プラス・インパクト銘柄|東証プライム|"
    r"Moomoo|前回の決算|決算は\d{1,2}月\d{1,2}日|"
    r"財務諸表だけでは勝てない|非構造化データ|日本トップが語る|"
    r"NISA|おすすめの?[^|｜。]*ETF|米国金融株ETF|高配当株ETF|"
    r"じぶん年金|今朝の5本|"
    r"インド株再評価|ドイツ、成長回復",
    flags=re.IGNORECASE,
)

THEME_PATTERNS = {
    "geopolitics_oil": r"停戦|停戦合意|ホルムズ|中東|イラン|イスラエル|報復|攻撃応酬|原油",
    "semiconductor": r"半導体|エヌビディア|NVIDIA|Micron|マイクロン|Broadcom|ブロードコム|SOX|AI",
    "rates": r"FRB|FOMC|金利|利下げ|利上げ|米国債|長期金利|パウエル",
    "macro": r"CPI|PCE|雇用統計|PMI|GDP|景気|インフレ",
    "index": r"米国株|米株|S&P500|Ｓ＆Ｐ５００|ナスダック|NASDAQ|NYダウ|ダウ",
    "fx": r"ドル円|為替|対ドル|円安|円高|介入|40年ぶり",
    "earnings": r"決算|業績|見通し|ガイダンス",
}


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
    title = strip_source_suffix(title)
    title = re.sub(r"（\s*(Bloomberg|ブルームバーグ)\s*）$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\(\s*(Bloomberg|ブルームバーグ)\s*\)$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", "", title.lower())
    return re.sub(r"[|｜:：\-ー–—].*$", "", title)


def read_url(url: str, *, headers: dict[str, str] | None = None, data: bytes | None = None) -> str:
    request_headers = {
        "User-Agent": "market-board-updater/1.0",
        "Accept": "application/rss+xml, application/xml, text/xml, application/json, text/html",
    }
    if headers:
        request_headers.update(headers)

    request = Request(url, data=data, headers=request_headers)
    with urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def find_child_text(element: ET.Element, name: str, namespaces: dict[str, str] | None = None) -> str:
    if namespaces:
        for prefix, uri in namespaces.items():
            child = element.find(f"{{{uri}}}{name}")
            if child is not None and child.text:
                return clean_text(child.text)

    child = element.find(name)
    if child is not None and child.text:
        return clean_text(child.text)
    return ""


def parse_rss_items(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        source = ""
        source_element = item.find("source")
        if source_element is not None and source_element.text:
            source = clean_text(source_element.text)

        items.append(
            {
                "title": find_child_text(item, "title"),
                "link": find_child_text(item, "link"),
                "published": find_child_text(item, "pubDate"),
                "summary": find_child_text(item, "description"),
                "source": source,
            }
        )
    return items


def fetch_news_candidates(max_articles: int = 100) -> list[Article]:
    articles: list[Article] = []
    seen: set[str] = set()

    def collect(query: str, *, japanese: bool) -> None:
        nonlocal articles
        xml_text = read_url(google_news_rss_url(query, japanese=japanese))
        for entry in parse_rss_items(xml_text):
            title = clean_text(entry.get("title", ""))
            url = entry.get("link", "")
            if not title or not url:
                continue
            source = clean_text(entry.get("source", "")) or "Google News"
            summary = clean_text(entry.get("summary", ""))
            if source in EXCLUDED_SOURCES:
                continue
            if EXCLUDE_NEWS_PATTERNS.search(" ".join([title, source, summary])):
                continue

            key = normalize_title(title)
            if key in seen:
                continue
            seen.add(key)

            articles.append(
                Article(
                    title=title,
                    url=url,
                    source=source,
                    published=clean_text(entry.get("published", "")),
                    language="ja" if japanese else "en",
                    summary=summary,
                )
            )

    for query in JAPANESE_QUERIES:
        collect(query, japanese=True)
        if len(articles) >= max_articles:
            break

    return articles[:max_articles]


def article_text(article: Article) -> str:
    return " ".join([article.title, article.source, article.summary])


def score_article(article: Article) -> int:
    text = article_text(article)
    score = 0
    for keyword, weight in IMPACT_KEYWORDS.items():
        if keyword.lower() in text.lower():
            score += weight
    for source, bonus in SOURCE_BONUS.items():
        if source.lower() in text.lower():
            score += bonus
    if article.language == "ja":
        score += 12
    if article.published:
        score += 4
    if is_bloombergish(article):
        score += 35
    if "米国市況" in text:
        score += 25
    return score


def is_bloombergish(article: Article) -> bool:
    text = article_text(article)
    return bool(
        re.search(
            r"Bloomberg|ブルームバーグ|TBS CROSS DIG with Bloomberg|TBS NEWS DIG",
            text,
            flags=re.IGNORECASE,
        )
    )


def article_theme(article: Article) -> str:
    text = article_text(article)
    for theme, pattern in THEME_PATTERNS.items():
        if re.search(pattern, text, flags=re.IGNORECASE):
            return theme
    return "other"


def strip_source_suffix(title: str) -> str:
    title = re.sub(r"\s+-\s+[^-]+$", "", title).strip()
    title = re.sub(r"\s+[|｜]\s+.+$", "", title).strip()
    return title


def make_headline(article: Article) -> str:
    headline = strip_source_suffix(article.title)
    headline = re.sub(r"^(米国株|米株)[:：]\s*", "", headline)
    headline = re.sub(r"\s+", " ", headline).strip()
    if len(headline) > 34:
        headline = headline[:33].rstrip() + "…"
    return headline


def make_summary(article: Article) -> str:
    title = strip_source_suffix(article.title)
    summary = clean_text(article.summary)
    summary = re.sub(r"\s+-\s+[^-]+$", "", summary).strip()
    summary = re.sub(r"^" + re.escape(title), "", summary).strip(" -:：")

    if (
        not summary
        or len(summary) < 25
        or summary.startswith("|")
        or re.fullmatch(r".*(TBS CROSS DIG with Bloomberg|TBS NEWS DIG|Yahoo!ニュース|Yahoo!ファイナンス).*", summary)
    ):
        summary = title

    summary = re.sub(r"\s+", " ", summary).strip()
    if len(summary) > 115:
        summary = summary[:114].rstrip() + "…"
    if not summary.endswith(("。", "…", "！", "？")):
        summary += "。"
    return summary


def display_source(article: Article) -> str:
    source = article.source or "ソース"
    text = article_text(article)
    if re.search(r"Bloomberg|ブルームバーグ", text, flags=re.IGNORECASE):
        if "TBS" in source:
            return "Bloomberg / TBS NEWS DIG"
        if "Yahoo" in source:
            return "Bloomberg / Yahoo!ファイナンス"
        if "Bloomberg" not in source and "ブルームバーグ" not in source:
            return f"Bloomberg / {source}"
    return source


def summarize_without_ai(articles: list[Article]) -> list[dict[str, str]]:
    if not articles:
        raise RuntimeError("No news candidates were found.")

    ranked = sorted(articles, key=score_article, reverse=True)
    selected: list[Article] = []
    used_themes: set[str] = set()
    used_titles: set[str] = set()
    priority_themes = {"index", "fx", "rates", "semiconductor", "geopolitics_oil"}

    for article in ranked:
        if not is_bloombergish(article):
            continue
        title_key = normalize_title(article.title)
        if title_key in used_titles:
            continue
        theme = article_theme(article)
        if theme not in priority_themes:
            continue
        if theme in used_themes and len(selected) < 3:
            continue
        selected.append(article)
        used_titles.add(title_key)
        used_themes.add(theme)
        if len(selected) == 3:
            break

    for article in ranked:
        if score_article(article) < 10:
            continue
        title_key = normalize_title(article.title)
        if title_key in used_titles:
            continue

        theme = article_theme(article)
        if theme in used_themes and len(selected) < 5:
            continue

        selected.append(article)
        used_titles.add(title_key)
        used_themes.add(theme)
        if len(selected) == 5:
            break

    if len(selected) < 5:
        for article in ranked:
            if article in selected:
                continue
            selected.append(article)
            if len(selected) == 5:
                break

    if "geopolitics_oil" not in {article_theme(article) for article in selected}:
        geopolitics = next(
            (
                article
                for article in ranked
                if article_theme(article) == "geopolitics_oil"
                and normalize_title(article.title) not in used_titles
                and score_article(article) >= 10
            ),
            None,
        )
        if geopolitics is not None:
            if len(selected) < 5:
                selected.append(geopolitics)
            else:
                selected[-1] = geopolitics

    return [
        {
            "headline": make_headline(article),
            "summary": make_summary(article),
            "url": article.url,
            "source": display_source(article),
        }
        for article in selected[:5]
    ]


def render_news_html(items: list[dict[str, str]]) -> str:
    generated_at = datetime.now(timezone.utc).astimezone(JST).strftime("%Y-%m-%d %H:%M %Z")
    blocks = [
        '<div style="display:flex;flex-direction:column;gap:14px;">',
        (
            '  <div style="margin:0 0 2px;color:#d6deee;font-size:14px;font-weight:800;line-height:1.6;">'
            f"最終更新: {html.escape(generated_at)}</div>"
        ),
    ]

    popup_blocks: list[str] = []

    for index, item in enumerate(items, start=1):
        popup_id = f"mb-news-{index}"
        headline = html.escape(item["headline"])
        summary = html.escape(item["summary"])
        url = html.escape(item["url"], quote=True)
        source = html.escape(item.get("source") or "ソース")
        blocks.extend(
            [
                '  <article style="background:#16233c;border:1px solid #3b4a66;border-radius:18px;padding:20px 22px;box-sizing:border-box;">',
                (
                    '    <h3 style="margin:0 0 10px;color:#ffffff;font-size:23px;line-height:1.35;font-weight:900;">'
                    f"{headline}</h3>"
                ),
                (
                    '    <p style="margin:0 0 10px;color:#d6deee;font-size:16px;font-weight:750;line-height:1.85;">'
                    f"{summary}</p>"
                ),
                (
                    f'    <a href="#{popup_id}" '
                    + 'style="display:inline-block;margin-top:4px;color:#7dd3fc;font-size:15px;font-weight:900;text-decoration:underline;">'
                    + f"ソース：{source}</a>"
                ),
                "  </article>",
            ]
        )
        popup_blocks.extend(
            [
                f'<section id="{popup_id}" class="market-board-popup">',
                '  <div class="market-board-popup-panel">',
                '    <div class="market-board-popup-header">',
                f"      <span>{source}：{headline}</span>",
                '      <a href="#market-board-top" class="market-board-popup-close">閉じる</a>',
                "    </div>",
                '    <div class="market-board-popup-body">',
                '      <div style="padding:26px;max-width:860px;margin:0 auto;color:#111827;box-sizing:border-box;">',
                '        <div style="margin:0 0 10px;color:#0369a1;font-size:14px;font-weight:900;">ニュースソース</div>',
                f'        <h3 style="margin:0 0 16px;color:#111827;font-size:28px;line-height:1.35;font-weight:900;">{headline}</h3>',
                f'        <p style="margin:0 0 22px;color:#1f2937;font-size:18px;line-height:1.9;font-weight:750;">{summary}</p>',
                '        <p style="margin:0 0 18px;color:#4b5563;font-size:14px;line-height:1.7;font-weight:700;">外部ニュースサイトはページ内表示を制限する場合があるため、この小窓ではライブ用の要約を表示します。</p>',
                f'        <a href="{url}" target="_blank" rel="noopener noreferrer" style="display:inline-block;background:#facc15;color:#111827;border-radius:12px;padding:12px 16px;font-size:16px;font-weight:900;text-decoration:none;">ソース記事を開く</a>',
                "      </div>",
                "    </div>",
                "  </div>",
                "</section>",
            ]
        )

    blocks.extend(["</div>", *popup_blocks])
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
    response_text = read_url(f"{url}?{urlencode({'context': 'edit'})}", headers=headers)
    return url, headers, json.loads(response_text)


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


def jst_board_date_label(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc).astimezone(JST)
    return f"{current.year}年{current.month}月{current.day}日（{JP_WEEKDAYS[current.weekday()]}）"


def refresh_static_date_labels(content: str) -> str:
    label = jst_board_date_label()
    content, header_count = re.subn(
        r'(<p style="margin:0 0 10px;color:#7dd3fc;font-size:18px;font-weight:900;">)'
        r"\d{4}年\d{1,2}月\d{1,2}日（[月火水木金土日]）"
        r"(</p>)",
        rf"\g<1>{label}\2",
        content,
        count=1,
    )
    content, lookahead_count = re.subn(
        r"(翌営業日チェック：)\d{4}年\d{1,2}月\d{1,2}日（[月火水木金土日]）",
        rf"\g<1>{label}",
        content,
        count=1,
    )
    content = re.sub(
        r"(CNN Business / 現在値はリンク先で確認)（確認\s+\d{2}/\d{2}\s+\d{2}:\d{2}\s+JST）",
        r"\1",
        content,
    )
    if header_count != 1:
        raise RuntimeError("Could not update the top-left board date label.")
    if lookahead_count != 1:
        raise RuntimeError("Could not update the next-session check date label.")
    return content


def update_wordpress_page(new_content: str) -> None:
    url, headers, _ = get_wordpress_page()
    payload: dict[str, Any] = {"content": new_content}

    read_url(url, headers=headers, data=json.dumps(payload).encode("utf-8"))


def build_news_html() -> str:
    articles = fetch_news_candidates()
    items = summarize_without_ai(articles)
    return render_news_html(items)


def update_html_file(path: Path, news_html: str) -> bool:
    current_content = path.read_text(encoding="utf-8")
    new_content = replace_auto_news_block(current_content, news_html)
    new_content = refresh_static_date_labels(new_content)
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
            refresh_static_date_labels(replace_auto_news_block(current_content, news_html))
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
    new_content = refresh_static_date_labels(new_content)
    update_wordpress_page(new_content)
    print("Updated WordPress market board news block.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
