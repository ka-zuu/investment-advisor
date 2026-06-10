"""週次バッチのエントリポイント（§12 実行フロー）。"""

from datetime import date

from investment_advisor import config
from investment_advisor.notion_client import NotionClient
from investment_advisor.portfolio.repository import (
    aggregate,
    load_active_holdings,
    load_latest_snapshot_before,
    load_year_start_snapshot,
)
from investment_advisor.portfolio.snapshot import create_and_save_snapshot
from investment_advisor.prd_loader import save_snapshot
from investment_advisor.sbi_csv.importer import run_import


def main() -> None:
    client = NotionClient()
    today = date.today()

    # Step 1-2: PRD読み込み＆スナップショット保存
    save_snapshot(client)

    # Step 2: 未設定DBのID解決
    config.resolve_db_ids(client)

    # Step 3-6: SBI CSV 取り込み
    run_import(client)

    # Step 7: ポートフォリオ集計
    holdings = load_active_holdings(client)
    prev_total = load_latest_snapshot_before(client, today)
    year_start_total = load_year_start_snapshot(client, today.year)
    summary = aggregate(holdings)
    summary.prev_total = prev_total
    summary.year_start_total = year_start_total
    print(f"[main] 総資産額: {summary.total_valuation:,.0f} 円")

    # Step 8: Portfolio Snapshot 保存
    create_and_save_snapshot(client, summary, today)

    # TODO(P1): Step 9 ニュース収集
    # TODO(P1): Step 10 過去レポート読み込み（答え合わせ）
    # TODO(P0): Step 11-14 エージェント分析
    # TODO(P0): Step 15-16 週次レポート生成＆Notion保存
    # TODO(P0): Step 17 実行ログ
    print("[main] 完了")


if __name__ == "__main__":
    main()
