"""ポートフォリオ集計モデル（§8.4 Portfolio Snapshots DB）。"""

from __future__ import annotations

from dataclasses import dataclass, field

# 株式として扱う資産クラス
_STOCK_CLASSES = {"日本株", "米国株", "ETF"}


@dataclass
class PortfolioSummary:
    total_valuation: float
    by_asset_class: dict[str, float] = field(default_factory=dict)
    by_currency: dict[str, float] = field(default_factory=dict)
    prev_total: float | None = None
    year_start_total: float | None = None

    def stock_ratio(self) -> float | None:
        if not self.total_valuation:
            return None
        stock = sum(v for k, v in self.by_asset_class.items() if k in _STOCK_CLASSES)
        return round(stock / self.total_valuation * 100, 2)

    def bond_ratio(self) -> float | None:
        if not self.total_valuation:
            return None
        return round(self.by_asset_class.get("債券", 0.0) / self.total_valuation * 100, 2)

    def cash_ratio(self) -> float | None:
        if not self.total_valuation:
            return None
        return round(self.by_asset_class.get("現金", 0.0) / self.total_valuation * 100, 2)

    def crypto_ratio(self) -> float | None:
        if not self.total_valuation:
            return None
        return round(self.by_asset_class.get("暗号資産", 0.0) / self.total_valuation * 100, 2)

    def jpy_ratio(self) -> float | None:
        if not self.total_valuation:
            return None
        return round(self.by_currency.get("JPY", 0.0) / self.total_valuation * 100, 2)

    def usd_ratio(self) -> float | None:
        if not self.total_valuation:
            return None
        return round(self.by_currency.get("USD", 0.0) / self.total_valuation * 100, 2)

    def wow_change(self) -> float | None:
        if self.prev_total is None or self.prev_total == 0:
            return None
        return round((self.total_valuation - self.prev_total) / self.prev_total * 100, 2)

    def ytd_change(self) -> float | None:
        if self.year_start_total is None or self.year_start_total == 0:
            return None
        return round((self.total_valuation - self.year_start_total) / self.year_start_total * 100, 2)
