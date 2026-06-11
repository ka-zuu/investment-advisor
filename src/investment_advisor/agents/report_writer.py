"""週次レポートの Notion ページ生成（Step 15-16）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from investment_advisor import config
from investment_advisor.agents.runner import AgentResult
from investment_advisor.notion_client import NotionClient
from investment_advisor.portfolio.models import PortfolioSummary
from investment_advisor.utils.money import format_jpy, format_pct


def create_report_stub(
    client: NotionClient,
    snapshot_page_id: str,
    ref_date: date,
) -> str:
    """Weekly Reports DB にスタブページを作成して page_id を返す。
    エージェント実行前にIDを確保し、分析結果からレポートへのRelationに使う。
    """
    props: dict[str, Any] = {
        "レポート名": {"title": [{"text": {"content": f"週次投資レポート {ref_date}"}}]},
        "対象週": {"date": {"start": ref_date.isoformat()}},
        "ステータス": {"status": {"name": "Draft"}},
        "作成日時": {"date": {"start": ref_date.isoformat()}},
    }
    if snapshot_page_id:
        props["Snapshot"] = {"relation": [{"id": snapshot_page_id}]}

    page = client.create_page(config.NOTION_DB_WEEKLY_REPORTS, props)
    page_id: str = page["id"]
    print(f"[report_writer] レポートスタブ作成: {ref_date} (id={page_id})")
    return page_id


def fill_report_content(
    client: NotionClient,
    report_page_id: str,
    summary: PortfolioSummary,
    persona_results: list[AgentResult],
    synth_result: AgentResult | None,
    ref_date: date,
) -> None:
    """レポートページに本文ブロックを追記し、総合評価プロパティを更新する。"""
    overall_rating = synth_result.overall_rating if synth_result else _vote_rating(persona_results)
    client.update_page(report_page_id, {"総合評価": {"select": {"name": overall_rating}}})

    blocks = _build_blocks(summary, persona_results, synth_result, ref_date)
    client.append_block_children(report_page_id, blocks)
    print(f"[report_writer] レポート本文書き込み完了: {ref_date}")


# ---------------------------------------------------------------------------
# ブロック構築
# ---------------------------------------------------------------------------


def _build_blocks(
    summary: PortfolioSummary,
    persona_results: list[AgentResult],
    synth_result: AgentResult | None,
    ref_date: date,
) -> list[dict[str, Any]]:
    b: list[dict[str, Any]] = []

    # 0. 振り返り（P1 未実装）
    b.append(_h2("0. 振り返り（答え合わせ）"))
    b.append(_para("（P1 未実装）1週間前・1か月前のAgent Analysis Resultsを参照した答え合わせは今後実装予定。"))

    # 1. 今週の総括
    b.append(_h2("1. 今週の総括"))
    b.append(_para(
        f"総資産額: {format_jpy(summary.total_valuation)}\n"
        f"前週比: {format_pct(summary.wow_change())}\n"
        f"年初来: {format_pct(summary.ytd_change())}"
    ))

    # 2. ポートフォリオ状況
    b.append(_h2("2. ポートフォリオ状況"))
    b.append(_h3("資産クラス別"))
    for asset_class, amount in sorted(summary.by_asset_class.items(), key=lambda x: -x[1]):
        pct = amount / summary.total_valuation * 100 if summary.total_valuation else 0
        b.append(_bullet(f"{asset_class}: {format_jpy(amount)} ({pct:.1f}%)"))
    b.append(_h3("通貨別"))
    for currency, amount in sorted(summary.by_currency.items(), key=lambda x: -x[1]):
        pct = amount / summary.total_valuation * 100 if summary.total_valuation else 0
        b.append(_bullet(f"{currency}: {format_jpy(amount)} ({pct:.1f}%)"))

    # 3. FIRE目標との差分
    b.append(_h2("3. FIRE目標との差分"))
    b.append(_para("（投資方針DBの目標値との照合はエージェントセクションの分析を参照）"))

    # 4. 保有銘柄関連ニュース（P1 未実装）
    b.append(_h2("4. 保有銘柄関連ニュース"))
    b.append(_para("（P1 未実装）Google News RSS / TDnet / FREDによる自動収集は今後実装予定。"))

    # 5. エージェント別コメント
    b.append(_h2("5. エージェント別コメント"))
    if persona_results:
        for r in persona_results:
            b.append(_h3(f"{r.agent_name} ― {r.overall_rating} / スコア: {r.score}"))
            b.append(_para(f"【要約】{r.summary}"))
            for chunk in _split(r.detail):
                b.append(_para(chunk))
            if r.actions:
                b.append(_para(f"【推奨アクション】\n{r.actions}"))
            if r.follow_up:
                b.append(_para(f"【要確認事項】\n{r.follow_up}"))
    else:
        b.append(_para("（エージェント未実行）"))

    # 6. 意見の対立（議長）
    b.append(_h2("6. 意見の対立"))
    if synth_result and synth_result.opinion_conflict:
        for chunk in _split(synth_result.opinion_conflict):
            b.append(_para(chunk))
    else:
        b.append(_para("（議長エージェント未実行）"))

    # 7. 今週の確認事項（議長）
    b.append(_h2("7. 今週の確認事項"))
    if synth_result and synth_result.weekly_checks:
        for chunk in _split(synth_result.weekly_checks):
            b.append(_para(chunk))
    else:
        b.append(_para("（議長エージェント未実行）"))

    # 8. アクション候補（議長）
    b.append(_h2("8. アクション候補"))
    if synth_result:
        if synth_result.action_immediate:
            b.append(_h3("すぐやる"))
            for chunk in _split(synth_result.action_immediate):
                b.append(_para(chunk))
        if synth_result.action_consider:
            b.append(_h3("検討する"))
            for chunk in _split(synth_result.action_consider):
                b.append(_para(chunk))
        if synth_result.action_skip:
            b.append(_h3("見送る"))
            for chunk in _split(synth_result.action_skip):
                b.append(_para(chunk))
    else:
        b.append(_para("（議長エージェント未実行）"))

    return b


def _vote_rating(results: list[AgentResult]) -> str:
    """ペルソナ結果の多数決で総合評価を決める（議長なし時のフォールバック）。"""
    counts: dict[str, int] = {}
    for r in results:
        counts[r.overall_rating] = counts.get(r.overall_rating, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else "注意"


# ---------------------------------------------------------------------------
# Notion ブロックヘルパー
# ---------------------------------------------------------------------------


def _h2(text: str) -> dict[str, Any]:
    return {
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
    }


def _h3(text: str) -> dict[str, Any]:
    return {
        "object": "block", "type": "heading_3",
        "heading_3": {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
    }


def _para(text: str) -> dict[str, Any]:
    return {
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
    }


def _bullet(text: str) -> dict[str, Any]:
    return {
        "object": "block", "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
    }


def _split(text: str, size: int = 1900) -> list[str]:
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]
