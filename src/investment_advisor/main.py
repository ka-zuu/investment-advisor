"""週次バッチのエントリポイント（§12 実行フロー）。"""

from investment_advisor import config
from investment_advisor.notion_client import NotionClient
from investment_advisor.prd_loader import save_snapshot


def main() -> None:
    client = NotionClient()

    # Step 1-2: PRD読み込み＆スナップショット保存
    save_snapshot(client)

    # Step 3: 未設定DBのID解決
    config.resolve_db_ids(client)

    # TODO(P0): Step 3-6 SBI CSV取り込み
    # TODO(P0): Step 7-8 ポートフォリオ集計＆スナップショット
    # TODO(P1): Step 9 ニュース収集
    # TODO(P1): Step 10 過去レポート読み込み（答え合わせ）
    # TODO(P0): Step 11-14 エージェント分析
    # TODO(P0): Step 15-16 週次レポート生成＆Notion保存
    print("[main] 完了")


if __name__ == "__main__":
    main()
