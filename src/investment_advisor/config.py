"""設定管理。.envを読み込み、未設定のNotion DB IDをAPIで解決する。"""

import os
from pathlib import Path

from dotenv import load_dotenv, set_key

_ENV_PATH = Path(__file__).parent.parent.parent / ".env"

load_dotenv(_ENV_PATH)

# --- Notion ---
NOTION_TOKEN: str = os.environ["NOTION_TOKEN"]
NOTION_PRD_PAGE_ID: str = os.environ.get("NOTION_PRD_PAGE_ID", "")
NOTION_IMPL_LOG_PAGE_ID: str = os.environ.get("NOTION_IMPL_LOG_PAGE_ID", "")

# Notion DB IDs（collection IDs）
NOTION_DB_SBI_CSV_IMPORT: str = os.environ.get("NOTION_DB_SBI_CSV_IMPORT", "")
NOTION_DB_ASSETS_MASTER: str = os.environ.get("NOTION_DB_ASSETS_MASTER", "")
NOTION_DB_HOLDINGS: str = os.environ.get("NOTION_DB_HOLDINGS", "")
NOTION_DB_INVESTMENT_POLICY: str = os.environ.get("NOTION_DB_INVESTMENT_POLICY", "")
NOTION_DB_AGENT: str = os.environ.get("NOTION_DB_AGENT", "")
NOTION_DB_AGENT_ANALYSIS: str = os.environ.get("NOTION_DB_AGENT_ANALYSIS", "")
NOTION_DB_WEEKLY_REPORTS: str = os.environ.get("NOTION_DB_WEEKLY_REPORTS", "")
NOTION_DB_PORTFOLIO_SNAPSHOTS: str = os.environ.get("NOTION_DB_PORTFOLIO_SNAPSHOTS", "")

# --- Claude API ---
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL_PERSONA: str = os.environ.get("MODEL_PERSONA", "claude-sonnet-4-6")
MODEL_SYNTHESIZER: str = os.environ.get("MODEL_SYNTHESIZER", "claude-opus-4-8")

# --- 実行設定 ---
TIMEZONE: str = os.environ.get("TIMEZONE", "Asia/Tokyo")

# DB名→envキーのマッピング（自動解決用）
_DB_NAME_TO_ENV: dict[str, str] = {
    "SBI CSV Import DB": "NOTION_DB_SBI_CSV_IMPORT",
    "Assets Master DB": "NOTION_DB_ASSETS_MASTER",
    "Holdings DB": "NOTION_DB_HOLDINGS",
    "Investment Policy DB": "NOTION_DB_INVESTMENT_POLICY",
    "Agent DB": "NOTION_DB_AGENT",
    "Agent Analysis Results DB": "NOTION_DB_AGENT_ANALYSIS",
    "Weekly Reports DB": "NOTION_DB_WEEKLY_REPORTS",
    "Portfolio Snapshots DB": "NOTION_DB_PORTFOLIO_SNAPSHOTS",
}


def resolve_db_ids(notion_client: "NotionClient") -> None:  # type: ignore[name-defined]
    """未設定のDB IDをNotionから検索して.envに書き込む。"""
    missing = {
        name: env_key
        for name, env_key in _DB_NAME_TO_ENV.items()
        if not os.environ.get(env_key)
    }
    if not missing:
        return

    for db_name, env_key in missing.items():
        db_id = notion_client.search_database_id(db_name)
        if db_id:
            os.environ[env_key] = db_id
            set_key(str(_ENV_PATH), env_key, db_id)
            print(f"[config] {env_key} = {db_id}  (resolved from Notion)")
        else:
            print(f"[config] WARNING: DB '{db_name}' not found in Notion")
