"""Holdings DB からの読み込みと集計（§8.3 / §8.4）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from investment_advisor import config
from investment_advisor.notion_client import NotionClient
from investment_advisor.portfolio.models import PortfolioSummary


def load_active_holdings(client: NotionClient) -> list[dict[str, Any]]:
    """Holdings DB の保有ステータス=Active な全行を取得する。"""
    return client.query_database(
        config.NOTION_DB_HOLDINGS,
        filter={"property": "保有ステータス", "status": {"equals": "Active"}},
    )


def aggregate(holdings: list[dict[str, Any]]) -> PortfolioSummary:
    """Holding リストを集計して PortfolioSummary を返す。前週・年初来は別途設定する。"""
    total = 0.0
    by_asset_class: dict[str, float] = {}
    by_currency: dict[str, float] = {}

    for page in holdings:
        props = page["properties"]
        valuation = (props.get("評価額") or {}).get("number") or 0.0
        asset_class = ((props.get("資産クラス") or {}).get("select") or {}).get("name") or "その他"
        currency = ((props.get("通貨") or {}).get("select") or {}).get("name") or "JPY"

        total += valuation
        by_asset_class[asset_class] = by_asset_class.get(asset_class, 0.0) + valuation
        by_currency[currency] = by_currency.get(currency, 0.0) + valuation

    return PortfolioSummary(
        total_valuation=total,
        by_asset_class=by_asset_class,
        by_currency=by_currency,
    )


def load_latest_snapshot_before(client: NotionClient, before_date: date) -> float | None:
    """Portfolio Snapshots DB から指定日より前の最新スナップショットの総資産額を返す。"""
    pages = client.query_database(
        config.NOTION_DB_PORTFOLIO_SNAPSHOTS,
        filter={"property": "日付", "date": {"before": before_date.isoformat()}},
        sorts=[{"property": "日付", "direction": "descending"}],
    )
    if not pages:
        return None
    return (pages[0]["properties"].get("総資産額") or {}).get("number")


def load_year_start_snapshot(client: NotionClient, year: int) -> float | None:
    """Portfolio Snapshots DB から指定年の最初のスナップショットの総資産額を返す。"""
    pages = client.query_database(
        config.NOTION_DB_PORTFOLIO_SNAPSHOTS,
        filter={
            "and": [
                {"property": "日付", "date": {"on_or_after": f"{year}-01-01"}},
                {"property": "日付", "date": {"before": f"{year}-12-31"}},
            ]
        },
        sorts=[{"property": "日付", "direction": "ascending"}],
    )
    if not pages:
        return None
    return (pages[0]["properties"].get("総資産額") or {}).get("number")
