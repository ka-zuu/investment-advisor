"""週次バッチのエントリポイント（§12 実行フロー）。"""

from datetime import date, timedelta

from investment_advisor import config
from investment_advisor.agents.prompts import build_lookback_context, load_investment_policy
from investment_advisor.agents.report_writer import create_report_stub, fill_report_content
from investment_advisor.agents.runner import run_all_agents
from investment_advisor.news.collector import collect_news
from investment_advisor.news.summarizer import summarize_news
from investment_advisor.notion_client import NotionClient
from investment_advisor.portfolio.fire import compute_fire_gap
from investment_advisor.portfolio.repository import (
    aggregate,
    load_active_holdings,
    load_latest_snapshot_before,
    load_latest_synth_analysis_before,
    load_year_start_snapshot,
)
from investment_advisor.portfolio.snapshot import create_and_save_snapshot
from investment_advisor.prd_loader import save_snapshot
from investment_advisor.sbi_csv.importer import run_import
from investment_advisor.utils.logging import log_weekly_execution


def main() -> None:
    from investment_advisor.agents.llm_adapter import make_adapter
    from investment_advisor.agents.runner import ExecutionStats

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
    snapshot_page_id = ""
    if config.NOTION_DB_PORTFOLIO_SNAPSHOTS:
        snapshot_page_id = create_and_save_snapshot(client, summary, today)
    else:
        print("[main] Portfolio Snapshot スキップ（NOTION_DB_PORTFOLIO_SNAPSHOTS未設定）")

    # Step 9: ニュース収集（P1 — Google News RSS + LLM要約）
    news_digest = None
    if holdings:
        adapter = make_adapter()
        stats_tmp = ExecutionStats()
        raw_news = collect_news(
            holdings,
            max_holdings=config.NEWS_MAX_HOLDINGS,
            max_articles=config.NEWS_MAX_ARTICLES,
        )
        if raw_news:
            from investment_advisor.agents.prompts import build_portfolio_context
            from investment_advisor.portfolio.fire import compute_fire_gap as _cgap
            policy_tmp = load_investment_policy(client)
            fire_tmp = _cgap(policy_tmp, summary.total_valuation, today)
            ctx_tmp = build_portfolio_context(summary, holdings, policy_tmp, fire_gap=fire_tmp)
            news_digest = summarize_news(adapter, raw_news, ctx_tmp, stats_tmp)
            print(f"[main] ニュース要約完了: {len(news_digest.items)} 件分類")
        else:
            print("[main] ニュース: 収集件数0のためスキップ")
    else:
        print("[main] ニュース: 保有銘柄なしのためスキップ")

    # Step 10: 過去レポート読み込み（P1 — 答え合わせ用・1週間前・1か月前）
    lookback_ctx = ""
    if config.NOTION_DB_AGENT_ANALYSIS:
        one_week = load_latest_synth_analysis_before(client, today - timedelta(days=5))
        one_month = load_latest_synth_analysis_before(client, today - timedelta(days=25))
        lookback_ctx = build_lookback_context(one_week, one_month, summary.total_valuation)
        if lookback_ctx:
            print("[main] 答え合わせ用過去データ読み込み完了")
        else:
            print("[main] 答え合わせ: 過去データなし（初回または DB未設定）")
    else:
        print("[main] 答え合わせ スキップ（NOTION_DB_AGENT_ANALYSIS未設定）")

    # FIRE差分計算
    policy = load_investment_policy(client)
    fire_gap = compute_fire_gap(policy, summary.total_valuation, today)

    # Step 15（スタブ作成）: エージェント実行前にレポートIDを確保する
    report_page_id = create_report_stub(client, snapshot_page_id, today)

    # Step 11-14: エージェント分析（ペルソナ4体→議長の2段階実行）
    persona_results, synth_result, stats = run_all_agents(
        client, summary, holdings, report_page_id, today,
        lookback_ctx=lookback_ctx,
        news_digest=news_digest,
    )

    # Step 15-16: レポート本文書き込み
    fill_report_content(
        client, report_page_id, summary, persona_results, synth_result, today,
        fire_gap=fire_gap,
        news_digest=news_digest,
    )

    # Step 17: 実行ログ
    log_weekly_execution(client, today, stats.runs)

    print(f"[main] 完了 (概算コスト: ~${stats.total_cost_usd():.4f} USD)")


if __name__ == "__main__":
    main()
