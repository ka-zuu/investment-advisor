"""ニュース収集モジュールのテスト（ネットワーク不要）。"""

from pathlib import Path
from unittest.mock import patch

import feedparser
import pytest

from investment_advisor.news.collector import (
    _build_search_targets,
    _fetch_news,
    collect_news,
)
from investment_advisor.news.models import NewsItem


FIXTURE_XML = (Path(__file__).parent / "fixtures" / "google_news_sample.xml").read_text(encoding="utf-8")

# フィクスチャXMLをモジュールレベルで1回だけパースしてキャッシュする。
# テストメソッド内で feedparser.parse() を直接呼ぶとネットワーク接続を試みる
# ケースがあるため、ここで変換しておいた結果を各テストが使い回す。
_PARSED_FEED = feedparser.parse(FIXTURE_XML)


def _make_holding(name: str, ext_id: str = "", valuation: float = 1_000_000) -> dict:
    return {
        "properties": {
            "保有名": {"title": [{"plain_text": name}]},
            "外部ID": {"rich_text": [{"plain_text": ext_id}] if ext_id else []},
            "評価額": {"number": valuation},
        }
    }


class TestBuildSearchTargets:
    def test_sorted_by_valuation_desc(self):
        holdings = [
            _make_holding("SBI株式", "8473", 500_000),
            _make_holding("オルカン", "", 10_000_000),
            _make_holding("日本国債", "", 3_000_000),
        ]
        targets = _build_search_targets(holdings, max_holdings=10)
        labels = [t[0] for t in targets]
        assert labels[0] == "オルカン"
        assert labels[1] == "日本国債"
        assert labels[2] == "SBI株式"

    def test_max_holdings_limit(self):
        holdings = [_make_holding(f"銘柄{i}", valuation=float(i)) for i in range(20)]
        targets = _build_search_targets(holdings, max_holdings=5)
        assert len(targets) == 5

    def test_query_with_ext_id(self):
        holdings = [_make_holding("SBI HD", "8473", 1_000_000)]
        targets = _build_search_targets(holdings, max_holdings=10)
        assert targets[0][1] == "8473 SBI HD"

    def test_query_without_ext_id(self):
        holdings = [_make_holding("オルカン", "", 1_000_000)]
        targets = _build_search_targets(holdings, max_holdings=10)
        assert targets[0][1] == "オルカン"

    def test_skip_empty_name(self):
        holdings = [_make_holding(""), _make_holding("有効銘柄")]
        targets = _build_search_targets(holdings, max_holdings=10)
        assert len(targets) == 1
        assert targets[0][0] == "有効銘柄"


class TestFetchNews:
    def test_max_articles_limit(self):
        with patch("investment_advisor.news.collector.feedparser.parse", return_value=_PARSED_FEED):
            items = _fetch_news("オルカン", "オルカン", max_articles=3)
        assert len(items) == 3

    def test_items_are_news_items(self):
        with patch("investment_advisor.news.collector.feedparser.parse", return_value=_PARSED_FEED):
            items = _fetch_news("オルカン", "オルカン", max_articles=5)
        assert all(isinstance(item, NewsItem) for item in items)

    def test_query_label_set(self):
        with patch("investment_advisor.news.collector.feedparser.parse", return_value=_PARSED_FEED):
            items = _fetch_news("オルカン", "オルカン", max_articles=2)
        assert all(item.query_label == "オルカン" for item in items)

    def test_title_and_link_populated(self):
        with patch("investment_advisor.news.collector.feedparser.parse", return_value=_PARSED_FEED):
            items = _fetch_news("オルカン", "オルカン", max_articles=5)
        for item in items:
            assert item.title
            assert item.link


class TestCollectNews:
    def test_deduplication(self):
        holdings = [
            _make_holding("オルカン", "", 10_000_000),
            _make_holding("オルカン", "", 5_000_000),  # 同一クエリ
        ]
        with patch("investment_advisor.news.collector.feedparser.parse", return_value=_PARSED_FEED):
            items = collect_news(holdings, max_holdings=10, max_articles=5)
        links = [item.link for item in items]
        assert len(links) == len(set(links))

    def test_network_error_skipped(self):
        holdings = [_make_holding("テスト銘柄")]
        with patch("investment_advisor.news.collector.feedparser.parse", side_effect=Exception("network error")):
            items = collect_news(holdings, max_holdings=10, max_articles=5)
        assert items == []

    def test_empty_holdings(self):
        items = collect_news([], max_holdings=10, max_articles=5)
        assert items == []
