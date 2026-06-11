"""Notion APIの薄いラッパ。DB クエリ・ページ作成・プロパティ更新のみ。"""

from __future__ import annotations

from typing import Any

from notion_client import Client

from investment_advisor import config


class NotionClient:
    def __init__(self) -> None:
        self._client = Client(auth=config.NOTION_TOKEN)
        self._db_id_cache: dict[str, str] = {}

    def _resolve_parent_db_id(self, data_source_id: str) -> str:
        """data_source_id から pages.create に必要な parent.database_id を解決してキャッシュする。
        notion-client v3 では data_source_id != database_id のため変換が必要。
        """
        if data_source_id not in self._db_id_cache:
            ds = self._client.data_sources.retrieve(data_source_id=data_source_id)
            parent = ds.get("parent", {})
            self._db_id_cache[data_source_id] = (
                parent["database_id"]
                if parent.get("type") == "database_id"
                else data_source_id
            )
        return self._db_id_cache[data_source_id]

    # ------------------------------------------------------------------
    # DB クエリ
    # ------------------------------------------------------------------

    def query_database(
        self,
        database_id: str,
        filter: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """DBの全ページを取得する（ページネーション自動処理）。
        notion-client v3 では databases.query が廃止され data_sources.query に移行。
        """
        results: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {"data_source_id": database_id}
        if filter:
            kwargs["filter"] = filter
        if sorts:
            kwargs["sorts"] = sorts

        while True:
            resp = self._client.data_sources.query(**kwargs)
            results.extend(resp["results"])
            if not resp.get("has_more"):
                break
            kwargs["start_cursor"] = resp["next_cursor"]

        return results

    def get_page(self, page_id: str) -> dict[str, Any]:
        return self._client.pages.retrieve(page_id=page_id)  # type: ignore[return-value]

    def get_block_children(self, block_id: str) -> list[dict[str, Any]]:
        """ブロックの子要素を全件取得する。"""
        results: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {"block_id": block_id}
        while True:
            resp = self._client.blocks.children.list(**kwargs)
            results.extend(resp["results"])
            if not resp.get("has_more"):
                break
            kwargs["start_cursor"] = resp["next_cursor"]
        return results

    # ------------------------------------------------------------------
    # ページ作成
    # ------------------------------------------------------------------

    def create_page(
        self,
        parent_database_id: str,
        properties: dict[str, Any],
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        actual_db_id = self._resolve_parent_db_id(parent_database_id)
        kwargs: dict[str, Any] = {
            "parent": {"database_id": actual_db_id},
            "properties": properties,
        }
        if children:
            kwargs["children"] = children
        return self._client.pages.create(**kwargs)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # プロパティ更新
    # ------------------------------------------------------------------

    def update_page(
        self,
        page_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        return self._client.pages.update(page_id=page_id, properties=properties)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # DB ID 解決（DB名で検索）
    # ------------------------------------------------------------------

    def search_database_id(self, db_name: str) -> str | None:
        """DB名（部分一致）でDBを検索し、最初にヒットしたDBのIDを返す。
        notion-client v3 では filter value が "data_source" に変更。
        """
        resp = self._client.search(
            query=db_name,
            filter={"property": "object", "value": "data_source"},
        )
        for result in resp.get("results", []):
            title_parts = result.get("title", [])
            title = "".join(p.get("plain_text", "") for p in title_parts)
            if db_name in title:
                return result["id"].replace("-", "")
        return None

    # ------------------------------------------------------------------
    # ブロック追記
    # ------------------------------------------------------------------

    def append_block_children(
        self,
        block_id: str,
        children: list[dict[str, Any]],
    ) -> None:
        """ページ（ブロック）に子ブロックを追記する。100件超は自動分割。"""
        batch_size = 100
        for i in range(0, len(children), batch_size):
            self._client.blocks.children.append(
                block_id=block_id,
                children=children[i : i + batch_size],
            )

    # ------------------------------------------------------------------
    # ファイルダウンロード補助
    # ------------------------------------------------------------------

    def get_file_url(self, page_id: str, files_property: str) -> str | None:
        """FilesプロパティからダウンロードURLを取得する。"""
        page = self.get_page(page_id)
        files = page["properties"].get(files_property, {}).get("files", [])
        if not files:
            return None
        file_obj = files[0]
        if file_obj["type"] == "file":
            return file_obj["file"]["url"]
        if file_obj["type"] == "external":
            return file_obj["external"]["url"]
        return None
