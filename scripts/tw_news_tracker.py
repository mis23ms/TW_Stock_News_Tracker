from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import requests
import xml.etree.ElementTree as ET


# -----------------------------
# Settings
# -----------------------------
TZ_TAIPEI = timezone(timedelta(hours=8))
DAYS_LOOKBACK = 7
NEWS_PER_STOCK = 3
REQUEST_SLEEP_SEC = 0.7

INCLUDE_KEYWORDS = ["財報", "營收", "法說會", "EPS"]
EXCLUDE_KEYWORDS = [
    "技術分析", "K線", "均線", "籌碼", "當沖", "飆股", "短線", "波段", "多空",
    "目標價", "操作", "選股", "盤中", "收盤", "漲停", "跌停", "買點", "賣點"
]

GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search"
GOOGLE_NEWS_PARAMS = {
    "hl": "zh-TW",
    "gl": "TW",
    "ceid": "TW:zh-Hant",
}

# TWSE OpenAPI: 公開發行公司每月營業收入彙總表
# Source: https://openapi.twse.com.tw/  (endpoint list)  :contentReference[oaicite:4]{index=4}
TWSE_MONTHLY_REVENUE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap46_L_7"

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "tw_stocks.json"
REPORTS_DIR = ROOT / "reports"
INDEX_PATH = ROOT / "index.md"


@dataclass
class NewsItem:
    stock_code: str
    stock_name: str
    title: str
    url: str
    published: Optional[datetime]  # in TZ_TAIPEI if parsed


def _now_tpe() -> datetime:
    return datetime.now(tz=TZ_TAIPEI)


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _load_stocks() -> List[Dict[str, str]]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_google_rss_url(company_name: str) -> str:
    # Use Google News search syntax in q (not officially documented).
    # We include keywords via OR, and also add "when:7d" but we *still* enforce pubDate filter in code.
    q = f'{company_name} ({ " OR ".join(INCLUDE_KEYWORDS) }) when:{DAYS_LOOKBACK}d'
    q_encoded = quote_plus(q)
    params = "&".join([f"{k}={quote_plus(v)}" for k, v in GOOGLE_NEWS_PARAMS.items()])
    return f"{GOOGLE_NEWS_RSS_BASE}?q={q_encoded}&{params}"


def _extract_text(elem: Optional[ET.Element]) -> str:
    return (elem.text or "").strip() if elem is not None else ""


def _parse_pubdate(pubdate_str: str) -> Optional[datetime]:
    if not pubdate_str:
        return None
    try:
        dt = parsedate_to_datetime(pubdate_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ_TAIPEI)
    except Exception:
        return None


def _title_passes_filters(title: str) -> bool:
    t = title.strip()
    if not t:
        return False

    # include: must contain at least one include keyword
    if not any(k in t for k in INCLUDE_KEYWORDS):
        return False

    # exclude: reject if contains any exclude keyword
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return False

    return True


def _resolve_final_url(session: requests.Session, url: str) -> str:
    # Google News RSS item link may be a google "articles/..." redirect.
    # Try to follow redirect once; if it fails, keep original.
    try:
        r = session.get(url, allow_redirects=True, timeout=12)
        r.raise_for_status()
        return r.url or url
    except Exception:
        return url


def _fetch_google_news_for_stock(
    session: requests.Session,
    stock_code: str,
    stock_name: str,
) -> List[NewsItem]:
    rss_url = _build_google_rss_url(stock_name)
    resp = session.get(rss_url, timeout=20)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)

    items: List[NewsItem] = []
    cutoff = _now_tpe() - timedelta(days=DAYS_LOOKBACK)

    # RSS is usually: <rss><channel><item>...</item></channel></rss>
    for item in root.findall(".//item"):
        title = _extract_text(item.find("title"))
        link = _extract_text(item.find("link"))
        pubdate = _extract_text(item.find("pubDate"))
        published = _parse_pubdate(pubdate)

        if not _title_passes_filters(title):
            continue

        if published is not None and published < cutoff:
            continue

        final_url = _resolve_final_url(session, link) if link else ""
        if not final_url:
            continue

        items.append(
            NewsItem(
                stock_code=stock_code,
                stock_name=stock_name,
                title=title,
                url=final_url,
                published=published,
            )
        )

        if len(items) >= NEWS_PER_STOCK:
            break

    return items


def _fetch_twse_monthly_revenue(session: requests.Session) -> Dict[str, Dict[str, str]]:
    """
    Returns dict keyed by 公司代號 (string) -> row dict
    """
    r = session.get(TWSE_MONTHLY_REVENUE_URL, timeout=30)
    r.raise_for_status()
    data = r.json()

    out: Dict[str, Dict[str, str]] = {}
    for row in data:
        code = str(row.get("公司代號", "")).strip()
        if code:
            out[code] = row
    return out


def _format_revenue_summary(row: Optional[Dict[str, str]]) -> str:
    if not row:
        return "月營收：找不到資料（TWSE OpenAPI 未回傳該公司代號）"

    # Common fields in t187ap46_L_7
    month_rev = str(row.get("當月營收", "")).strip()
    mom = str(row.get("上月比較增減(%)", "")).strip()
    yoy = str(row.get("去年同月增減(%)", "")).strip()

    cum_rev = str(row.get("累計營收", "")).strip()
    cum_yoy = str(row.get("前期比較增減(%)", "")).strip()

    # Keep it simple & robust even if fields are missing
    parts = []
    if month_rev:
        parts.append(f"單月 {month_rev}")
    if mom:
        parts.append(f"MoM {mom}%")
    if yoy:
        parts.append(f"YoY {yoy}%")

    parts2 = []
    if cum_rev:
        parts2.append(f"累計 {cum_rev}")
    if cum_yoy:
        parts2.append(f"累計YoY {cum_yoy}%")

    s1 = " / ".join(parts) if parts else "單月（無數值）"
    s2 = " / ".join(parts2) if parts2 else "累計（無數值）"
    return f"月營收：{s1}；{s2}"


def _render_report(
    report_date: datetime,
    all_news: List[NewsItem],
    stocks: List[Dict[str, str]],
    revenue_map: Dict[str, Dict[str, str]],
) -> str:
    date_str = report_date.strftime("%Y-%m-%d")

    # URL list for NotebookLM (deduped)
    seen = set()
    url_list: List[str] = []
    for n in all_news:
        if n.url not in seen:
            seen.add(n.url)
            url_list.append(n.url)

    # Group news by stock code
    by_code: Dict[str, List[NewsItem]] = {}
    for n in all_news:
        by_code.setdefault(n.stock_code, []).append(n)

    lines: List[str] = []
    lines.append(f"# 台股追蹤 — {date_str}")
    lines.append("")
    lines.append("## 📋 Copy URLs for NotebookLM")
    lines.append("")
    lines.append("Copy the URLs below and paste them into NotebookLM as sources:")
    lines.append("")
    lines.append("```")
    for u in url_list:
        lines.append(u)  # URL text only
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📊 詳細報告")
    lines.append("")

    for s in stocks:
        code = s["code"]
        name = s["name"]
        lines.append(f"### {code} {name}")

        rev_row = revenue_map.get(code)
        lines.append(f"- 📈 {_format_revenue_summary(rev_row)}")

        items = by_code.get(code, [])
        if not items:
            lines.append("- 📰（7天內無符合條件新聞）")
            lines.append("")
            continue

        for it in items[:NEWS_PER_STOCK]:
            # Keep as link markdown for readability, but URL remains plain text in the NotebookLM section
            lines.append(f"- 📰 [{it.title}]({it.url})")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _update_index(latest_report_relpath: str) -> None:
    """
    Keep a simple index that points to latest report + recent list.
    No deletions, no external calls.
    """
    REPORTS_DIR.glob("*.md")
    report_files = sorted([p for p in REPORTS_DIR.glob("*.md") if p.name != ".gitkeep"], reverse=True)

    lines: List[str] = []
    lines.append("# 台股新聞追蹤（財報/營收/法說/EPS）")
    lines.append("")
    lines.append(f"- 最新報告：[{latest_report_relpath}]({latest_report_relpath})")
    lines.append("")
    lines.append("## 歷史報告")
    lines.append("")
    for p in report_files[:30]:
        rel = f"reports/{p.name}"
        lines.append(f"- [{p.name}]({rel})")

    INDEX_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    _safe_mkdir(REPORTS_DIR)

    stocks = _load_stocks()
    report_date = _now_tpe()
    report_name = report_date.strftime("%Y-%m-%d") + ".md"
    report_path = REPORTS_DIR / report_name

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "TW-Stock-News-Tracker/1.0 (+https://github.com/)",
            "Accept": "*/*",
        }
    )

    # Monthly revenue (once per run)
    revenue_map = _fetch_twse_monthly_revenue(session)

    all_news: List[NewsItem] = []
    for s in stocks:
        code = s["code"]
        name = s["name"]

        try:
            news = _fetch_google_news_for_stock(session, code, name)
        except Exception:
            news = []

        all_news.extend(news)
        time.sleep(REQUEST_SLEEP_SEC)

    # Dedup across stocks by URL (keep first occurrence)
    deduped: List[NewsItem] = []
    seen = set()
    for n in all_news:
        if n.url in seen:
            continue
        seen.add(n.url)
        deduped.append(n)

    content = _render_report(report_date, deduped, stocks, revenue_map)
    report_path.write_text(content, encoding="utf-8")

    _update_index(f"reports/{report_name}")


if __name__ == "__main__":
    main()
