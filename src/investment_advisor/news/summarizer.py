"""収集したニュースを LLM で要約・分類し NewsDigest を生成する（§9.8）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from investment_advisor import config
from investment_advisor.news.models import ClassifiedNews, NewsDigest, NewsItem

if TYPE_CHECKING:
    from investment_advisor.agents.llm_adapter import _BaseAdapter
    from investment_advisor.agents.runner import ExecutionStats


_NEWS_TOOL: dict[str, Any] = {
    "name": "submit_news_digest",
    "description": "保有銘柄関連ニュースの要約・分類結果を構造化して提出する",
    "input_schema": {
        "type": "object",
        "properties": {
            "narrative": {
                "type": "string",
                "description": (
                    "週次レポートの「保有銘柄関連ニュース」節に掲載する通し要約。"
                    "マクロは独立章にせず保有銘柄への含意に翻訳した形でのみ記載する。"
                    "投資判断を断定しない。"
                ),
            },
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "記事タイトル（原文）"},
                        "link": {"type": "string", "description": "記事URL"},
                        "related_holding": {"type": "string", "description": "関連する保有銘柄名"},
                        "category": {
                            "type": "string",
                            "enum": ["決算", "開示", "マクロ", "業界", "その他"],
                            "description": "ニュースの分類",
                        },
                        "implication": {
                            "type": "string",
                            "description": "保有銘柄への含意（断定表現は使わない）",
                        },
                        "importance": {
                            "type": "string",
                            "enum": ["高", "中", "低"],
                            "description": "重要度",
                        },
                    },
                    "required": ["title", "link", "related_holding", "category", "implication", "importance"],
                },
                "description": "分類済みニュース一覧",
            },
        },
        "required": ["narrative", "items"],
    },
}

_SYSTEM = (
    "あなたは個人投資家のポートフォリオ担当アナリストです。"
    "提供されたニュース見出し一覧を、保有銘柄への含意に翻訳・分類してください。\n"
    "遵守事項：\n"
    "- 投資判断を断定しない（「必ず上がる」「買うべき」等の表現は使わない）\n"
    "- マクロニュースは独立章にせず、保有銘柄・資産クラスへの含意に翻訳した形でのみ記載\n"
    "- 根拠・不確実性・反対解釈を含める\n"
    "- 最終判断はユーザーが行う前提で書く"
)


def summarize_news(
    adapter: "_BaseAdapter",
    items: list[NewsItem],
    portfolio_ctx: str,
    stats: "ExecutionStats",
) -> NewsDigest:
    """収集した NewsItem を LLM で要約・分類して NewsDigest を返す。"""
    model = config.LLM_MODEL_NEWS or config.LLM_MODEL_PERSONA
    news_text = _format_items(items)
    user_content = f"{portfolio_ctx}\n\n## 収集したニュース見出し\n{news_text}"

    try:
        resp = adapter.complete_with_tool(
            model=model,
            max_tokens=4000,
            system=_SYSTEM,
            user_content=user_content,
            tool=_NEWS_TOOL,
        )
    except Exception as e:
        print(f"[news] ニュース要約 LLM エラー: {e}")
        return NewsDigest(narrative=f"（ニュース要約に失敗しました: {e}）")

    stats.record("ニュース要約", config.LLM_PROVIDER, model, resp.input_tokens, resp.output_tokens)

    if not resp.tool_input:
        print("[news] ニュース要約: tool 呼び出しなし")
        return NewsDigest(narrative="（ニュース要約の結果が得られませんでした）")

    data = resp.tool_input
    classified = [
        ClassifiedNews(
            title=it.get("title", ""),
            link=it.get("link", ""),
            related_holding=it.get("related_holding", ""),
            category=it.get("category", "その他"),
            implication=it.get("implication", ""),
            importance=it.get("importance", "低"),
        )
        for it in data.get("items", [])
    ]
    return NewsDigest(narrative=data.get("narrative", ""), items=classified)


def _format_items(items: list[NewsItem]) -> str:
    lines = []
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. [{item.query_label}] {item.title}（{item.source}）{item.link}")
    return "\n".join(lines)
