"""Google News RSS から保有銘柄関連ニュースを収集する（§9.8）。"""

from __future__ import annotations

import urllib.parse
from typing import Any

import feedparser

from investment_advisor.news.models import NewsItem


def collect_news(
    holdings: list[dict[str, Any]],
    max_holdings: int = 10,
    max_articles: int = 5,
) -> list[NewsItem]:
    """保有銘柄（評価額降順 max_holdings 件）について Google News RSS を検索し NewsItem リストを返す。"""
    search_targets = _build_search_targets(holdings, max_holdings)
    items: list[NewsItem] = []
    seen: set[tuple[str, str]] = set()  # (link, normalized_title) で重複排除

    for query_label, query in search_targets:
        try:
            fetched = _fetch_news(query, query_label, max_articles)
        except Exception as e:
            print(f"[news] '{query_label}' のニュース取得をスキップ: {e}")
            continue
        for item in fetched:
            key = (item.link, item.title.strip().lower())
            if key not in seen:
                seen.add(key)
                items.append(item)

    print(f"[news] {len(search_targets)} 銘柄を検索、計 {len(items)} 件取得")
    return items


def _build_search_targets(
    holdings: list[dict[str, Any]],
    max_holdings: int,
) -> list[tuple[str, str]]:
    """holdings を評価額降順にソートし、上位 max_holdings 件の検索クエリリストを返す。"""
    scored: list[tuple[float, str, str]] = []
    for page in holdings:
        props = page.get("properties", {})
        # 資産名（title）
        name_parts = (props.get("保有名") or {}).get("title") or []
        name = "".join(p.get("plain_text", "") for p in name_parts).strip()
        # 外部ID（ティッカー/コード）
        ext_id_parts = (props.get("外部ID") or {}).get("rich_text") or []
        ext_id = "".join(p.get("plain_text", "") for p in ext_id_parts).strip()
        valuation = (props.get("評価額") or {}).get("number") or 0.0

        if not name:
            continue
        # ティッカーがあれば「ティッカー 銘柄名」、なければ銘柄名のみ
        query = f"{ext_id} {name}".strip() if ext_id else name
        label = name
        scored.append((valuation, label, query))

    scored.sort(key=lambda x: -x[0])
    return [(label, query) for _, label, query in scored[:max_holdings]]


def _fetch_news(query: str, query_label: str, max_articles: int) -> list[NewsItem]:
    import httpx
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ja&gl=JP&ceid=JP:ja"
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    items: list[NewsItem] = []
    for entry in feed.entries[:max_articles]:
        items.append(NewsItem(
            title=entry.get("title", ""),
            link=entry.get("link", ""),
            source=entry.get("source", {}).get("title", "") if isinstance(entry.get("source"), dict) else "",
            published=entry.get("published", ""),
            query_label=query_label,
        ))
    return items
