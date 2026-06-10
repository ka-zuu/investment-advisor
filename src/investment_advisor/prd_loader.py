"""PRD読み込み＆スナップショット保存。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from investment_advisor import config
from investment_advisor.notion_client import NotionClient

_SNAPSHOT_PATH = Path(__file__).parent.parent.parent / "docs" / "prd.snapshot.md"


def load_prd(client: NotionClient) -> str:
    """NotionのPRDページをMarkdownテキストとして返す。"""
    page_id = config.NOTION_PRD_PAGE_ID
    if not page_id:
        raise ValueError("NOTION_PRD_PAGE_ID が未設定です")

    blocks = client.get_block_children(page_id)
    lines: list[str] = [
        f"# PRD Snapshot — {date.today().isoformat()}",
        f"Source: https://app.notion.com/p/{page_id.replace('-', '')}",
        "",
    ]
    lines.extend(_blocks_to_markdown(blocks, client))
    return "\n".join(lines)


def save_snapshot(client: NotionClient) -> Path:
    """PRDをdocs/prd.snapshot.mdに保存し、パスを返す。"""
    text = load_prd(client)
    _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SNAPSHOT_PATH.write_text(text, encoding="utf-8")
    print(f"[prd_loader] PRDスナップショットを保存しました: {_SNAPSHOT_PATH}")
    return _SNAPSHOT_PATH


# ------------------------------------------------------------------
# Notion block → Markdown 変換（基本ブロックのみ対応）
# ------------------------------------------------------------------

def _blocks_to_markdown(
    blocks: list[dict[str, Any]],
    client: NotionClient,
    depth: int = 0,
) -> list[str]:
    lines: list[str] = []
    indent = "  " * depth

    for block in blocks:
        btype = block["type"]
        content = block.get(btype, {})

        if btype == "paragraph":
            text = _rich_text(content.get("rich_text", []))
            lines.append(f"{indent}{text}" if text else "")

        elif btype in ("heading_1", "heading_2", "heading_3"):
            level = int(btype[-1])
            text = _rich_text(content.get("rich_text", []))
            lines.append(f"\n{'#' * level} {text}")

        elif btype == "bulleted_list_item":
            text = _rich_text(content.get("rich_text", []))
            lines.append(f"{indent}- {text}")

        elif btype == "numbered_list_item":
            text = _rich_text(content.get("rich_text", []))
            lines.append(f"{indent}1. {text}")

        elif btype == "code":
            lang = content.get("language", "")
            text = _rich_text(content.get("rich_text", []))
            lines.extend([f"```{lang}", text, "```"])

        elif btype == "callout":
            text = _rich_text(content.get("rich_text", []))
            lines.append(f"> {text}")

        elif btype == "divider":
            lines.append("---")

        elif btype == "table":
            lines.extend(_table_to_markdown(block, client))

        elif btype == "child_page":
            # 子ページはスナップショット対象外（リンクのみ表示）
            title = content.get("title", "")
            lines.append(f"- [{title}]")
            continue

        # 子ブロックを再帰処理
        if block.get("has_children") and btype not in ("table", "child_page"):
            children = client.get_block_children(block["id"])
            lines.extend(_blocks_to_markdown(children, client, depth + 1))

    return lines


def _rich_text(rich_texts: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for rt in rich_texts:
        text = rt.get("plain_text", "")
        annotations = rt.get("annotations", {})
        if annotations.get("bold"):
            text = f"**{text}**"
        if annotations.get("code"):
            text = f"`{text}`"
        parts.append(text)
    return "".join(parts)


def _table_to_markdown(
    table_block: dict[str, Any],
    client: NotionClient,
) -> list[str]:
    rows = client.get_block_children(table_block["id"])
    lines: list[str] = []
    for i, row in enumerate(rows):
        cells = row.get("table_row", {}).get("cells", [])
        row_text = "| " + " | ".join(_rich_text(cell) for cell in cells) + " |"
        lines.append(row_text)
        if i == 0:
            sep = "| " + " | ".join("---" for _ in cells) + " |"
            lines.append(sep)
    return lines
