from __future__ import annotations

from datetime import date
from typing import Any

from investment_advisor import config
from investment_advisor.notion_client import NotionClient

# USD/MTok 単価テーブル (input_rate, output_rate)
_COST_TABLE: dict[str, tuple[float, float]] = {
    # Gemini
    "gemini-2.0-flash":        (0.10,  0.40),
    "gemini-2.0-flash-001":    (0.10,  0.40),
    "gemini-2.5-flash":        (0.15,  0.60),
    "gemini-2.5-pro":          (1.25, 10.00),
    "gemini-3.5-flash":        (0.15,  0.60),   # 概算（正式料金は公式参照）
    "gemini-3.1-pro-preview":  (1.25, 10.00),   # 概算（正式料金は公式参照）
    "gemini-3.1-flash-lite":   (0.10,  0.40),
    # Claude
    "claude-sonnet-4-6":       (3.0,  15.0),
    "claude-opus-4-7":         (15.0, 75.0),
    "claude-opus-4-8":         (15.0, 75.0),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = _COST_TABLE.get(model, (3.0, 15.0))
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


def log_weekly_execution(
    client: NotionClient,
    run_date: date,
    runs: list[dict[str, Any]],
) -> None:
    """実行ログ（週次バッチ）をNotionの実装ログページに追記する。"""
    if not config.NOTION_IMPL_LOG_PAGE_ID:
        print("[logging] NOTION_IMPL_LOG_PAGE_ID未設定のためスキップ")
        return

    total_cost = 0.0
    detail_lines: list[str] = []
    for r in runs:
        in_tok = r.get("input_tokens", 0)
        out_tok = r.get("output_tokens", 0)
        model = r.get("model", "")
        cost = estimate_cost_usd(model, in_tok, out_tok)
        total_cost += cost
        detail_lines.append(
            f"  {r.get('agent', '?')} | {model} | in={in_tok} out={out_tok} | ~${cost:.4f}"
        )

    text = (
        f"【{run_date} 週次バッチ】 実行{len(runs)}件 / 合計概算 ~${total_cost:.4f} USD\n"
        + "\n".join(detail_lines)
    )

    client.append_block_children(
        config.NOTION_IMPL_LOG_PAGE_ID,
        [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
                },
            }
        ],
    )
    print(f"[logging] 実行ログ記録完了 (概算コスト: ~${total_cost:.4f} USD)")
