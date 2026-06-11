"""週次レポートの Notion ページ生成（Step 15-16）。"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from investment_advisor import config
from investment_advisor.agents.runner import AgentResult
from investment_advisor.notion_client import NotionClient
from investment_advisor.portfolio.models import PortfolioSummary
from investment_advisor.utils.money import format_jpy, format_pct

if TYPE_CHECKING:
    from investment_advisor.news.models import NewsDigest
    from investment_advisor.portfolio.fire import FireGap


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
    fire_gap: "FireGap | None" = None,
    news_digest: "NewsDigest | None" = None,
) -> None:
    """レポートページに本文ブロックを追記し、総合評価プロパティを更新する。"""
    overall_rating = synth_result.overall_rating if synth_result else _vote_rating(persona_results)
    client.update_page(report_page_id, {"総合評価": {"select": {"name": overall_rating}}})

    blocks = _build_blocks(summary, persona_results, synth_result, ref_date, fire_gap=fire_gap, news_digest=news_digest)
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
    fire_gap: "FireGap | None" = None,
    news_digest: "NewsDigest | None" = None,
) -> list[dict[str, Any]]:
    b: list[dict[str, Any]] = []

    # 0. 振り返り（答え合わせ）
    b.append(_h2("0. 振り返り（答え合わせ）"))
    if synth_result and synth_result.lookback_review:
        for chunk in _split(synth_result.lookback_review):
            b.append(_para(chunk))
    else:
        b.append(_para("（過去データなし、または初回実行のため対象なし）"))

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
    if fire_gap:
        b.append(_bullet(f"現在総資産: {format_jpy(fire_gap.current)}"))
        if fire_gap.target_assets is not None:
            b.append(_bullet(f"目標資産額: {format_jpy(fire_gap.target_assets)}"))
        if fire_gap.progress_pct is not None:
            b.append(_bullet(f"進捗: {fire_gap.progress_pct:.1f}%"))
        if fire_gap.gap is not None:
            b.append(_bullet(f"残り差額: {format_jpy(fire_gap.gap)}"))
        if fire_gap.target_year is not None:
            b.append(_bullet(f"FIRE目標年: {fire_gap.target_year}年（残り{fire_gap.years_left}年）"))
        if fire_gap.required_cagr is not None:
            b.append(_bullet(f"必要CAGR（入金なし単純複利）: {fire_gap.required_cagr:.2f}%/年"))
        if fire_gap.annual_contribution is not None:
            b.append(_bullet(f"年間入金額: {format_jpy(fire_gap.annual_contribution)}"))
        if fire_gap.contribution_covers_pct is not None:
            b.append(_bullet(f"入金累計カバー率: {fire_gap.contribution_covers_pct:.1f}%（残り期間×年間入金÷差額）"))
    else:
        b.append(_para("（投資方針DBに目標資産額・FIRE目標年・毎月入金額を設定するとここに表示されます）"))

    # 4. 保有銘柄関連ニュース
    b.append(_h2("4. 保有銘柄関連ニュース"))
    if news_digest and (news_digest.narrative or news_digest.items):
        if news_digest.narrative:
            for chunk in _split(news_digest.narrative):
                b.append(_para(chunk))
        for item in news_digest.items:
            importance_mark = {"高": "★★★", "中": "★★", "低": "★"}.get(item.importance, "★")
            b.append(_bullet(
                f"{importance_mark}【{item.category}】{item.related_holding}: {item.implication}\n"
                f"  → {item.title}  {item.link}"
            ))
    else:
        b.append(_para("（今週は対象ニュースなし）"))

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
    if persona_results:
        scores = [r.score for r in persona_results]
        spread = max(scores) - min(scores) if scores else 0
        b.append(_para(f"スコアレンジ: {min(scores)}〜{max(scores)}（差={spread}点）"))
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
