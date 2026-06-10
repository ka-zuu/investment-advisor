"""SbiRow → Notion Holdings DB プロパティへのマッピング（§8.3 / §9.3 / §9.4）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from investment_advisor.sbi_csv.parser import SbiRow


def to_holding_properties(
    row: SbiRow,
    reference_date: date,
) -> dict[str, Any]:
    """SbiRow を Notion ページのプロパティ辞書に変換する。"""
    cost_amount = _calc_cost_amount(row)
    holding_name = _make_holding_name(row)

    props: dict[str, Any] = {
        "保有名": {"title": [{"text": {"content": holding_name}}]},
        "データソース": {"select": {"name": "SBI_CSV"}},
        "口座": {"select": {"name": row.account}},
        "資産クラス": {"select": {"name": row.asset_class}},
        "通貨": {"select": {"name": "JPY"}},
        "保有ステータス": {"status": {"name": "Active"}},
        "基準日": {"date": {"start": reference_date.isoformat()}},
        "最終更新日": {"date": {"start": date.today().isoformat()}},
    }

    if row.external_id:
        props["外部ID"] = {"rich_text": [{"text": {"content": row.external_id}}]}

    if row.quantity is not None:
        props["数量"] = {"number": row.quantity}

    if row.cost_price is not None:
        props["平均取得単価"] = {"number": row.cost_price}

    if row.current_price is not None:
        props["現在価格"] = {"number": row.current_price}

    if cost_amount is not None:
        props["取得額"] = {"number": cost_amount}

    if row.valuation is not None:
        props["評価額"] = {"number": row.valuation}

    if row.gain_loss is not None:
        props["評価損益"] = {"number": row.gain_loss}

    if row.gain_loss_pct is not None:
        props["評価損益率"] = {"number": row.gain_loss_pct}

    return props


def make_primary_key(row: SbiRow) -> str:
    """主キー文字列を返す。データソース + 口座 + 外部ID/資産名（§9.5）。"""
    identifier = row.external_id or row.name
    return f"SBI_CSV|{row.account}|{identifier}"


def _calc_cost_amount(row: SbiRow) -> float | None:
    """取得額を算出する（CSVに取得額列は無い）。

    株式：取得単価 × 数量
    投信：取得単価 × 数量 ÷ 10000（口数・1万口あたり単価）
    国内債券：保有額面 × 取得単価 ÷ 100
    """
    if row.cost_price is None or row.quantity is None:
        return None

    if row.asset_class == "投信":
        return row.cost_price * row.quantity / 10000
    if row.asset_class == "債券":
        face = row.face_value
        if face is None:
            return None
        return face * row.cost_price / 100
    return row.cost_price * row.quantity


def _make_holding_name(row: SbiRow) -> str:
    """保有名文字列を生成する。"""
    return f"{row.name} ({row.account})"
