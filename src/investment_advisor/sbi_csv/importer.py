"""SBI CSV → Holdings DB インポーター（§8.1 / §8.3 / §9）。

Manual行は絶対に上書き・削除しない。
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from investment_advisor import config
from investment_advisor.notion_client import NotionClient
from investment_advisor.sbi_csv.mapper import make_primary_key, to_holding_properties
from investment_advisor.sbi_csv.parser import SbiRow, parse_csv


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"作成:{self.created} 更新:{self.updated} "
            f"スキップ:{self.skipped} エラー:{len(self.errors)}"
        )


def run_import(client: NotionClient) -> None:
    """未処理のSBI CSV ImportレコードをすべてHoldings DBに取り込む。"""
    db_id = config.NOTION_DB_SBI_CSV_IMPORT
    pending = client.query_database(
        db_id,
        filter={
            "and": [
                {"property": "ステータス", "status": {"equals": "未処理"}},
                {"property": "種別", "select": {"equals": "保有資産"}},
            ]
        },
    )
    print(f"[importer] 未処理CSV: {len(pending)} 件")

    for record in pending:
        page_id = record["id"]
        name = _title(record)
        print(f"[importer] 処理開始: {name}")
        try:
            result = _process_record(client, record)
            client.update_page(
                page_id,
                {
                    "ステータス": {"status": {"name": "処理済み"}},
                    "処理日時": {"date": {"start": date.today().isoformat()}},
                    "インポート結果": {
                        "rich_text": [{"text": {"content": str(result)}}]
                    },
                },
            )
            print(f"[importer] 完了: {name} — {result}")
        except Exception as exc:
            client.update_page(
                page_id,
                {
                    "ステータス": {"status": {"name": "エラー"}},
                    "処理日時": {"date": {"start": date.today().isoformat()}},
                    "エラー内容": {
                        "rich_text": [{"text": {"content": str(exc)}}]
                    },
                },
            )
            print(f"[importer] エラー: {name} — {exc}")


def _process_record(
    client: NotionClient,
    record: dict[str, Any],
) -> ImportResult:
    page_id = record["id"]

    # 対象日を取得
    ref_date_str = (
        record["properties"]
        .get("対象日", {})
        .get("date", {})
        or {}
    ).get("start")
    ref_date = date.fromisoformat(ref_date_str) if ref_date_str else date.today()

    # CSVファイルURLを取得してダウンロード
    file_url = client.get_file_url(page_id, "CSVファイル")
    if not file_url:
        raise ValueError("CSVファイルが添付されていません")

    csv_bytes = httpx.get(file_url, follow_redirects=True).content

    # パース
    rows, parse_errors = parse_csv(io.BytesIO(csv_bytes))
    result = ImportResult(errors=parse_errors)

    if not rows and parse_errors:
        raise ValueError("CSVパース失敗: " + "; ".join(parse_errors[:3]))

    # 既存Holdings（SBI_CSV）を主キーでキャッシュ
    existing = _load_existing_sbi_holdings(client)

    # 今回CSVに存在した主キーを記録（Not in latest CSV 更新用）
    seen_keys: set[str] = set()

    for row in rows:
        key = make_primary_key(row)
        seen_keys.add(key)
        props = to_holding_properties(row, ref_date)
        try:
            if key in existing:
                client.update_page(existing[key], props)
                result.updated += 1
            else:
                client.create_page(config.NOTION_DB_HOLDINGS, props)
                result.created += 1
        except Exception as exc:
            result.errors.append(f"{row.name}: {exc}")
            result.skipped += 1

    # 今回CSVに無い既存SBI行を「Not in latest CSV」に更新
    for key, page_id_existing in existing.items():
        if key not in seen_keys:
            try:
                client.update_page(
                    page_id_existing,
                    {"保有ステータス": {"status": {"name": "Not in latest CSV"}}},
                )
            except Exception as exc:
                result.errors.append(f"Not in latest CSV 更新失敗 ({key}): {exc}")

    return result


def _load_existing_sbi_holdings(client: NotionClient) -> dict[str, str]:
    """Holdings DB の SBI_CSV 行を {主キー: page_id} で返す。Manual行は含まない。"""
    pages = client.query_database(
        config.NOTION_DB_HOLDINGS,
        filter={"property": "データソース", "select": {"equals": "SBI_CSV"}},
    )
    result: dict[str, str] = {}
    for page in pages:
        props = page["properties"]
        account = props.get("口座", {}).get("select", {}) or {}
        account_name = account.get("name", "")
        ext_id_parts = props.get("外部ID", {}).get("rich_text", [])
        ext_id = ext_id_parts[0]["plain_text"] if ext_id_parts else ""
        title_parts = props.get("保有名", {}).get("title", [])
        holding_name = title_parts[0]["plain_text"] if title_parts else ""
        # 資産名を保有名から逆引き（"名前 (口座)" 形式）
        asset_name = holding_name.replace(f" ({account_name})", "").strip()
        identifier = ext_id or asset_name
        key = f"SBI_CSV|{account_name}|{identifier}"
        result[key] = page["id"]
    return result


def _title(record: dict[str, Any]) -> str:
    parts = record["properties"].get("名前", {}).get("title", [])
    return parts[0]["plain_text"] if parts else record["id"]
