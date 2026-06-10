"""SBI CSVのみを手動実行するスクリプト。"""

from investment_advisor.notion_client import NotionClient
from investment_advisor.sbi_csv.importer import run_import

if __name__ == "__main__":
    client = NotionClient()
    run_import(client)
