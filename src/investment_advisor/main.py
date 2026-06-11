"""週次バッチのエントリポイント（§12 実行フロー）。"""

from datetime import date

from investment_advisor import config
from investment_advisor.agents.report_writer import create_report_stub, fill_report_content
from investment_advisor.agents.runner import run_all_agents
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
from investment_advisor.utils.logging import log_weekly_execution


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

    # Step 8: Portfolio Snapshot 保存（P1 — DB未設定時はスキップ）
    snapshot_page_id = ""
    if config.NOTION_DB_PORTFOLIO_SNAPSHOTS:
        snapshot_page_id = create_and_save_snapshot(client, summary, today)
    else:
        print("[main] Portfolio Snapshot スキップ（P1: NOTION_DB_PORTFOLIO_SNAPSHOTS未設定）")

    # TODO(P1): Step 9 ニュース収集（Google News RSS / TDnet / FRED）
    # TODO(P1): Step 10 過去レポート読み込み（1週間前・1か月前の答え合わせ）

    # Step 15（スタブ作成）: エージェント実行前にレポートIDを確保する
    report_page_id = create_report_stub(client, snapshot_page_id, today)

    # Step 11-14: エージェント分析（ペルソナ4体→議長の2段階実行）
    persona_results, synth_result, stats = run_all_agents(
        client, summary, holdings, report_page_id, today
    )

    # Step 15-16: レポート本文書き込み
    fill_report_content(client, report_page_id, summary, persona_results, synth_result, today)

    # Step 17: 実行ログ
    log_weekly_execution(client, today, stats.runs)

    print(f"[main] 完了 (概算コスト: ~${stats.total_cost_usd():.4f} USD)")


if __name__ == "__main__":
    main()
