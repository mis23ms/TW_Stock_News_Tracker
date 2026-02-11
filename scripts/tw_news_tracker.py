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
DAYS_LOOKBACK = int(os.getenv("DAYS_LOOKBACK", "7"))
NEWS_PER_STOCK = int(os.getenv("NEWS_PER_STOCK", "3"))

INCLUDE_KEYWORDS = ["財報", "營收", "法說會", "EPS"]
EXCLUDE_KEYWORDS = [
    "技術分析", "K線", "均線", "籌碼", "當沖", "飆股", "短線", "波段", "多空",
    "目標價", "操作", "選股", "盤中", "收盤", "漲停", "跌停", "買點", "賣點",
    "facebook", "FB", "YouTube", "影片", "懶人包", "直播",
]

GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search"
GOOGLE_NEWS_PARAMS = {
    "hl": "zh-TW",
    "gl": "TW",
    "ceid": "TW:zh-Hant",
}

# 上市每月營收彙總
TWSE_MONTHLY_REVENUE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
# 上櫃每月營收彙總
TPEX_MONTHLY_REVENUE_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"

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
    return datetime.now(TZ_TAIPEI)


def _get_first(row: Dict[str, str], keys: List[str]) -> str:
    """Return the first non-empty value among candidate keys."""
    for k in keys:
        v = str(row.get(k, "")).strip()
        if v:
            return v
    return ""


def _fmt_int_like(s: str) -> str:
    """Format numeric-looking strings with commas; keep original if not int."""
    try:
        if s.isdigit():
            return f"{int(s):,}"
        if re.fullmatch(r"\d+\.0+", s):
            return f"{int(float(s)):,}"
    except Exception:
        pass
    return s


def _build_google_rss_url(company_name: str) -> str:
    # q format example: 台積電 (財報 OR 營收 OR 法說會 OR EPS) when:7d
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

    # include keyword
    if not any(k in t for k in INCLUDE_KEYWORDS):
        return False

    # exclude keyword
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return False

    return True


def _resolve_final_url(session: requests.Session, url: str) -> str:
    # Google News RSS item link may be a google "articles/..." redirect.
    # Try to follow redirect; if it fails, keep original.
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

    for item in root.findall(".//item"):
        title = _extract_text(item.find("title"))
        link = _extract_text(item.find("link"))
        pubdate = _extract_text(item.find("pubDate"))
        published = _parse_pubdate(pubdate)

        if not _title_passes_filters(title):
            continue

        # 確保標題真的提到這家公司（避免抓到別家公司）
        if (stock_name not in title) and (stock_code not in title):
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


def _fetch_monthly_revenue(session: requests.Session) -> Dict[str, Dict[str, str]]:
    """Fetch latest monthly revenue for listed (TWSE) + OTC (TPEX), keyed by stock code."""
    out: Dict[str, Dict[str, str]] = {}

    def _load(url: str) -> List[Dict[str, str]]:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []

    for url in [TWSE_MONTHLY_REVENUE_URL, TPEX_MONTHLY_REVENUE_URL]:
        try:
            data = _load(url)
    except Exception as e:
        print(f"[WARN] 月營收 API 失敗: {url} → {e}")
        continue

        for row in data:
            code = str(row.get("公司代號", "")).strip()
            if code:
                out[code] = row

    return out


def _format_revenue_summary(row: Optional[Dict[str, str]]) -> str:
    if not row:
        return "月營收：找不到資料（OpenAPI 無該公司代號資料）"

    month_rev = _get_first(row, ["當月營收", "營業收入-當月營收"])
    mom = _get_first(row, ["上月比較增減(%)", "營業收入-上月比較增減(%)"])
    yoy = _get_first(row, ["去年同月增減(%)", "營業收入-去年同月增減(%)"])

    cum_rev = _get_first(row, ["累計營收", "營業收入-累計營收"])
    cum_yoy = _get_first(row, ["前期比較增減(%)", "營業收入-前期比較增減(%)"])

    parts = []
    if month_rev:
        parts.append(f"單月 {_fmt_int_like(month_rev)}")
    if mom:
        parts.append(f"MoM {mom}%")
    if yoy:
        parts.append(f"YoY {yoy}%")

    parts2 = []
    if cum_rev:
        parts2.append(f"累計 {_fmt_int_like(cum_rev)}")
    if cum_yoy:
        parts2.append(f"累計YoY {cum_yoy}%")

    s1 = " / ".join(parts) if parts else "單月（無數值）"
    s2 = " / ".join(parts2) if parts2 else "累計（無數值）"
    return f"月營收：{s1}；{s2}"


def _load_stocks() -> List[Dict[str, str]]:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("config/tw_stocks.json must be a list")
    return data


def _render_report(
    date_str: str,
    all_news: List[NewsItem],
    revenue_map: Dict[str, Dict[str, str]],
) -> Tuple[str, List[str]]:
    url_list: List[str] = []
    for n in all_news:
        url_list.append(n.url)

    # URL 去重（保持順序）
    seen = set()
    url_list = [u for u in url_list if not (u in seen or seen.add(u))]

    # group news by stock
    by_stock: Dict[Tuple[str, str], List[NewsItem]] = {}
    for n in all_news:
        by_stock.setdefault((n.stock_code, n.stock_name), []).append(n)

    lines: List[str] = []
    lines.append(f"# 台股追蹤 — {date_str}")
    lines.append("")
    lines.append("## 📋 Copy URLs for NotebookLM")
    lines.append("")
    for u in url_list:
        lines.append(u)  # URL text only

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📊 詳細報告")
    lines.append("")

    for (code, name), items in by_stock.items():
        lines.append(f"### {code} {name}")
        lines.append(f"- 📈 {_format_revenue_summary(revenue_map.get(code))}")
        for it in items:
            lines.append(f"- 📰 [{it.title}]({it.url})")
        lines.append("")

    return "\n".join(lines).strip() + "\n", url_list


def _write_report(md_text: str, date_str: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"{date_str}.md"
    out_path.write_text(md_text, encoding="utf-8")
    return out_path


def _write_index(latest_report_path: Path, date_str: str) -> None:
    # simple index that links to latest report for GitHub Pages
    rel = latest_report_path.name
    content = f"# TW_Stock_News_Tracker\n\n- 最新報告：[{date_str}](reports/{rel})\n"
    INDEX_PATH.write_text(content, encoding="utf-8")


def main() -> None:
    stocks = _load_stocks()
    date_str = _now_tpe().strftime("%Y-%m-%d")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.3",
    })

    # 先抓月營收（上市+上櫃）
    revenue_map = _fetch_monthly_revenue(session)

    all_news: List[NewsItem] = []
    for s in stocks:
        code = str(s.get("證券代號", "")).strip()
        name = str(s.get("證券名稱", "")).strip()
        if not code or not name:
            continue

        try:
            items = _fetch_google_news_for_stock(session, code, name)
        except Exception:
            items = []

        all_news.extend(items)
        time.sleep(0.8)  # avoid rate limit

    md_text, _ = _render_report(date_str, all_news, revenue_map)
    report_path = _write_report(md_text, date_str)
    _write_index(report_path, date_str)


if __name__ == "__main__":
    main()
