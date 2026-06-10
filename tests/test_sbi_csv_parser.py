"""SBI CSVパーサのテスト。"""

import io
from pathlib import Path

import pytest

from investment_advisor.sbi_csv.parser import parse_csv, SECTION_MAP

FIXTURES = Path(__file__).parent / "fixtures"


def _encode_fixture(csv_text: str) -> bytes:
    """テスト用CSVをcp932に変換する。"""
    return csv_text.encode("cp932", errors="replace")


def _load_sample() -> bytes:
    path = FIXTURES / "sbi_sample.csv"
    text = path.read_text(encoding="utf-8")
    return _encode_fixture(text)


def test_parse_sample_row_count() -> None:
    rows, errors = parse_csv(io.BytesIO(_load_sample()))
    # 株式1行 + 投信1行 + 債券1行
    assert len(rows) == 3, f"errors: {errors}"


def test_parse_stock_row() -> None:
    rows, _ = parse_csv(io.BytesIO(_load_sample()))
    stock = next(r for r in rows if r.asset_class == "日本株")
    assert stock.external_id == "9999"
    assert stock.name == "サンプル株式"
    assert stock.account == "SBI特定"
    assert stock.quantity == 100.0
    assert stock.cost_price == 1000.0
    assert stock.current_price == 1200.0
    assert stock.gain_loss == 20000.0
    assert stock.gain_loss_pct == 20.0
    assert stock.valuation == 120000.0


def test_parse_fund_row() -> None:
    rows, _ = parse_csv(io.BytesIO(_load_sample()))
    fund = next(r for r in rows if r.asset_class == "投信")
    assert fund.external_id is None
    assert "全世界株" in fund.name
    assert fund.quantity == 1000000.0
    assert fund.cost_price == 15000.0
    assert fund.valuation == 1800000.0


def test_parse_bond_row() -> None:
    rows, _ = parse_csv(io.BytesIO(_load_sample()))
    bond = next(r for r in rows if r.asset_class == "債券")
    assert bond.account == "SBI特定"
    assert bond.face_value == 1000000.0
    assert bond.cost_price == 98.50
    assert bond.valuation == 985000.0


def _nel_bytes(csv_text: str) -> bytes:
    """テキストをcp932エンコードし、\x85を生バイト0x85として埋め込む。"""
    parts = csv_text.split("\x85")
    encoded = [p.encode("cp932", errors="replace") for p in parts]
    return b"\x85".join(encoded)


def test_nel_treated_as_newline() -> None:
    """生バイト0x85（NEL相当）が改行として扱われること。"""
    csv_text = (
        "ポートフォリオ一覧\x85一括表示\x85PTS株価非表示\x85総件数：1件\x85選択範囲：全て\x85ページ：1\x85"
        "株式（現物/特定預り）\x85"
        '"銘柄（コード）","買付日","数量","取得単価","現在値","前日比","前日比（％）","損益","損益（％）","評価額"\x85'
        '"1234 テスト株","2024/01/01","50","500","600","＋10","＋2.00","＋5000","＋20.00","30000"\x85'
    )
    rows, errors = parse_csv(io.BytesIO(_nel_bytes(csv_text)))
    assert len(rows) == 1, f"errors: {errors}"
    assert rows[0].external_id == "1234"
    assert rows[0].quantity == 50.0


def test_no_manual_rows_affected() -> None:
    """Manual行はパーサの対象外（CSVに含まれない）。"""
    rows, _ = parse_csv(io.BytesIO(_load_sample()))
    for row in rows:
        assert row.account != "Manual"


def test_section_map_completeness() -> None:
    """§9.2 のセクションがすべてSECTION_MAPに含まれること。"""
    expected = {
        "株式（現物/特定預り）",
        "株式（現物/NISA預り（成長投資枠））",
        "投資信託（金額/特定預り）",
        "投資信託（金額/NISA預り（成長投資枠））",
        "投資信託（金額/NISA預り（つみたて投資枠））",
        "投資信託（金額/旧NISA預り）",
        "国内債券（特定預り）",
    }
    assert expected == set(SECTION_MAP.keys())
