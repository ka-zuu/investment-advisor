"""SBI CSV → Notion プロパティ変換のテスト。"""

from datetime import date

from investment_advisor.sbi_csv.mapper import (
    _calc_cost_amount,
    make_primary_key,
    to_holding_properties,
)
from investment_advisor.sbi_csv.parser import SbiRow


def _stock_row(**kwargs) -> SbiRow:  # type: ignore[no-untyped-def]
    defaults = dict(
        asset_class="日本株",
        account="SBI特定",
        name="テスト株",
        external_id="9999",
        quantity=100.0,
        cost_price=1000.0,
        current_price=1200.0,
        gain_loss=20000.0,
        gain_loss_pct=20.0,
        valuation=120000.0,
    )
    defaults.update(kwargs)
    return SbiRow(**defaults)


def test_cost_amount_stock() -> None:
    row = _stock_row(asset_class="日本株", quantity=100.0, cost_price=1000.0)
    assert _calc_cost_amount(row) == 100000.0


def test_cost_amount_fund() -> None:
    row = _stock_row(
        asset_class="投信",
        external_id=None,
        quantity=1_000_000.0,
        cost_price=15000.0,
    )
    assert _calc_cost_amount(row) == 1_500_000.0


def test_cost_amount_bond() -> None:
    row = _stock_row(
        asset_class="債券",
        external_id=None,
        quantity=1_000_000.0,
        face_value=1_000_000.0,
        cost_price=98.50,
        current_price=None,
        gain_loss=None,
        gain_loss_pct=None,
        valuation=985000.0,
    )
    assert _calc_cost_amount(row) == 985_000.0


def test_primary_key_with_external_id() -> None:
    row = _stock_row()
    assert make_primary_key(row) == "SBI_CSV|SBI特定|9999"


def test_primary_key_without_external_id() -> None:
    row = _stock_row(external_id=None, name="オルカン")
    assert make_primary_key(row) == "SBI_CSV|SBI特定|オルカン"


def test_to_holding_properties_data_source_is_sbi_csv() -> None:
    row = _stock_row()
    props = to_holding_properties(row, date(2026, 6, 10))
    assert props["データソース"]["select"]["name"] == "SBI_CSV"


def test_to_holding_properties_never_sets_manual() -> None:
    row = _stock_row()
    props = to_holding_properties(row, date(2026, 6, 10))
    # データソースがSBI_CSV固定であること
    assert props["データソース"]["select"]["name"] != "Manual"
