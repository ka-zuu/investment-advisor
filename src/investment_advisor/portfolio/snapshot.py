"""Portfolio Snapshot の Notion 保存（§8.4 Portfolio Snapshots DB）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from investment_advisor import config
from investment_advisor.notion_client import NotionClient
from investment_advisor.portfolio.models import PortfolioSummary


def create_and_save_snapshot(
    client: NotionClient,
    summary: PortfolioSummary,
    ref_date: date,
) -> str:
    """集計結果を Portfolio Snapshots DB に保存し、page_id を返す。"""
    props: dict[str, Any] = {
        "Snapshot名": {"title": [{"text": {"content": f"Portfolio Snapshot {ref_date}"}}]},
        "日付": {"date": {"start": ref_date.isoformat()}},
        "総資産額": {"number": summary.total_valuation},
    }

    _set_if_not_none(props, "前週比", summary.wow_change())
    _set_if_not_none(props, "年初来", summary.ytd_change())
    _set_if_not_none(props, "株式比率", summary.stock_ratio())
    _set_if_not_none(props, "債券比率", summary.bond_ratio())
    _set_if_not_none(props, "現金比率", summary.cash_ratio())
    _set_if_not_none(props, "暗号資産比率", summary.crypto_ratio())
    _set_if_not_none(props, "JPY比率", summary.jpy_ratio())
    _set_if_not_none(props, "USD比率", summary.usd_ratio())

    page = client.create_page(config.NOTION_DB_PORTFOLIO_SNAPSHOTS, props)
    page_id: str = page["id"]
    print(f"[snapshot] Portfolio Snapshot 保存完了: {ref_date} (id={page_id})")
    return page_id


def _set_if_not_none(props: dict[str, Any], key: str, value: float | None) -> None:
    if value is not None:
        props[key] = {"number": value}
