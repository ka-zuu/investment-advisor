"""ポートフォリオ集計ロジックのテスト。"""

from investment_advisor.portfolio.models import PortfolioSummary
from investment_advisor.portfolio.repository import aggregate


def _make_holding(
    valuation: float,
    asset_class: str = "日本株",
    currency: str = "JPY",
) -> dict:
    """テスト用 Holding ページ辞書を生成する。"""
    return {
        "properties": {
            "評価額": {"number": valuation},
            "資産クラス": {"select": {"name": asset_class}},
            "通貨": {"select": {"name": currency}},
        }
    }


def test_aggregate_empty_holdings() -> None:
    summary = aggregate([])
    assert summary.total_valuation == 0.0
    assert summary.stock_ratio() is None
    assert summary.wow_change() is None


def test_aggregate_single_stock() -> None:
    holdings = [_make_holding(1_000_000, "日本株", "JPY")]
    summary = aggregate(holdings)
    assert summary.total_valuation == 1_000_000
    assert summary.stock_ratio() == 100.0
    assert summary.bond_ratio() == 0.0
    assert summary.jpy_ratio() == 100.0
    assert summary.usd_ratio() == 0.0


def test_aggregate_mixed_assets() -> None:
    holdings = [
        _make_holding(600_000, "日本株", "JPY"),
        _make_holding(200_000, "債券", "JPY"),
        _make_holding(200_000, "投信", "JPY"),
    ]
    summary = aggregate(holdings)
    assert summary.total_valuation == 1_000_000
    assert summary.stock_ratio() == 60.0
    assert summary.bond_ratio() == 20.0
    assert summary.cash_ratio() == 0.0


def test_aggregate_etf_counted_as_stock() -> None:
    holdings = [
        _make_holding(500_000, "ETF", "USD"),
        _make_holding(500_000, "米国株", "USD"),
    ]
    summary = aggregate(holdings)
    assert summary.stock_ratio() == 100.0


def test_aggregate_jpy_usd_ratio() -> None:
    holdings = [
        _make_holding(700_000, "日本株", "JPY"),
        _make_holding(300_000, "米国株", "USD"),
    ]
    summary = aggregate(holdings)
    assert summary.total_valuation == 1_000_000
    assert summary.jpy_ratio() == 70.0
    assert summary.usd_ratio() == 30.0


def test_wow_change() -> None:
    summary = PortfolioSummary(total_valuation=1_100_000, prev_total=1_000_000)
    assert summary.wow_change() == 10.0


def test_ytd_change() -> None:
    summary = PortfolioSummary(total_valuation=1_200_000, year_start_total=1_000_000)
    assert summary.ytd_change() == 20.0


def test_wow_change_none_when_no_prev() -> None:
    summary = PortfolioSummary(total_valuation=1_000_000, prev_total=None)
    assert summary.wow_change() is None


def test_aggregate_missing_fields_defaults() -> None:
    """資産クラス・通貨プロパティが未設定の Holding は「その他」「JPY」扱いにする。"""
    holding = {"properties": {"評価額": {"number": 500_000}}}
    summary = aggregate([holding])
    assert summary.total_valuation == 500_000
    assert summary.by_asset_class.get("その他") == 500_000
    assert summary.by_currency.get("JPY") == 500_000
