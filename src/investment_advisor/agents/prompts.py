from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from investment_advisor import config
from investment_advisor.notion_client import NotionClient
from investment_advisor.portfolio.models import PortfolioSummary
from investment_advisor.utils.money import format_jpy, format_pct

if TYPE_CHECKING:
    from investment_advisor.agents.runner import AgentResult
    from investment_advisor.news.models import NewsDigest
    from investment_advisor.portfolio.fire import FireGap


def load_investment_policy(client: NotionClient) -> dict[str, str]:
    """Investment Policy DB から方針一覧を {項目: 値} で返す。"""
    if not config.NOTION_DB_INVESTMENT_POLICY:
        return {}
    pages = client.query_database(config.NOTION_DB_INVESTMENT_POLICY)
    policy: dict[str, str] = {}
    for page in pages:
        props = page["properties"]
        key = _rich_text(props, "項目", title=True)
        val = _rich_text(props, "値")
        if key:
            policy[key] = val
    return policy


def build_portfolio_context(
    summary: PortfolioSummary,
    holdings: list[dict[str, Any]],
    policy: dict[str, str],
    news_digest: "NewsDigest | None" = None,
    fire_gap: "FireGap | None" = None,
) -> str:
    lines = [
        "## ポートフォリオ現況",
        f"総資産額: {format_jpy(summary.total_valuation)}",
        f"前週比: {format_pct(summary.wow_change())}",
        f"年初来: {format_pct(summary.ytd_change())}",
        "",
        "### 資産クラス別",
    ]
    for asset_class, amount in sorted(summary.by_asset_class.items(), key=lambda x: -x[1]):
        pct = amount / summary.total_valuation * 100 if summary.total_valuation else 0
        lines.append(f"- {asset_class}: {format_jpy(amount)} ({pct:.1f}%)")

    lines += ["", "### 通貨別"]
    for currency, amount in sorted(summary.by_currency.items(), key=lambda x: -x[1]):
        pct = amount / summary.total_valuation * 100 if summary.total_valuation else 0
        lines.append(f"- {currency}: {format_jpy(amount)} ({pct:.1f}%)")

    lines += ["", "### 保有銘柄一覧"]
    for page in holdings:
        props = page["properties"]
        name = _rich_text(props, "保有名", title=True)
        valuation = (props.get("評価額") or {}).get("number") or 0.0
        pnl = (props.get("評価損益") or {}).get("number")
        pnl_pct = (props.get("評価損益率") or {}).get("number")
        account = ((props.get("口座") or {}).get("select") or {}).get("name") or ""
        asset_class = ((props.get("資産クラス") or {}).get("select") or {}).get("name") or ""
        pnl_str = format_jpy(pnl) if pnl is not None else "N/A"
        pnl_pct_str = format_pct(pnl_pct) if pnl_pct is not None else "N/A"
        lines.append(
            f"- {name} [{asset_class}/{account}]: "
            f"評価額={format_jpy(valuation)}  損益={pnl_str}({pnl_pct_str})"
        )

    if fire_gap:
        lines += ["", "## FIRE目標との差分"]
        lines.append(f"- 現在総資産: {format_jpy(fire_gap.current)}")
        if fire_gap.target_assets is not None:
            lines.append(f"- 目標資産額: {format_jpy(fire_gap.target_assets)}")
        if fire_gap.progress_pct is not None:
            lines.append(f"- 進捗: {fire_gap.progress_pct:.1f}%")
        if fire_gap.gap is not None:
            lines.append(f"- 残り差額: {format_jpy(fire_gap.gap)}")
        if fire_gap.target_year is not None:
            lines.append(f"- FIRE目標年: {fire_gap.target_year}年（残り{fire_gap.years_left}年）")
        if fire_gap.required_cagr is not None:
            lines.append(f"- 必要CAGR（入金なし）: {fire_gap.required_cagr:.2f}%/年")
        if fire_gap.contribution_covers_pct is not None:
            lines.append(f"- 入金累計カバー率: {fire_gap.contribution_covers_pct:.1f}%（残り期間×年間入金/差額）")

    if policy:
        lines += ["", "## 投資方針"]
        for k, v in policy.items():
            if v:
                lines.append(f"- {k}: {v}")

    if news_digest and (news_digest.narrative or news_digest.items):
        lines += ["", "## 保有銘柄関連ニュース"]
        if news_digest.narrative:
            lines.append(news_digest.narrative)
        for item in news_digest.items:
            lines.append(
                f"- [{item.category}/{item.importance}] {item.related_holding}: {item.implication}（{item.title}）"
            )

    return "\n".join(lines)


def build_synthesizer_context(persona_results: list[AgentResult]) -> str:
    lines = ["## 各エージェントの分析結果"]
    for r in persona_results:
        lines += [
            f"### {r.agent_name}  (評価: {r.overall_rating} / スコア: {r.score})",
            f"**要約**: {r.summary}",
            f"**詳細分析**: {r.detail}",
            f"**推奨アクション**: {r.actions}",
            f"**要確認事項**: {r.follow_up}",
            "",
        ]
    lines += [
        "---",
        "上記4エージェントの評価が割れている点（攻める vs 守る、高スコア vs 低スコアなど）を "
        "`opinion_conflict` フィールドで具体名・総合評価・スコアを挙げて明示してください。",
    ]
    return "\n".join(lines)


def build_lookback_context(
    one_week: dict[str, Any] | None,
    one_month: dict[str, Any] | None,
    current_total: float,
) -> str:
    """1週間前・1か月前の議長分析を整形し、答え合わせ用コンテキストを返す。"""
    if not one_week and not one_month:
        return ""

    lines = ["## 過去レポート（答え合わせ用）"]

    def _extract(page: dict[str, Any], label: str) -> None:
        props = page.get("properties", {})
        date_val = (props.get("日付") or {}).get("date", {}) or {}
        date_str = date_val.get("start", "不明")
        summary_parts = (props.get("要約") or {}).get("rich_text") or []
        summary = "".join(p.get("plain_text", "") for p in summary_parts)
        actions_parts = (props.get("推奨アクション") or {}).get("rich_text") or []
        actions = "".join(p.get("plain_text", "") for p in actions_parts)
        lines += [
            f"### {label}（{date_str}）",
            f"要約: {summary or '（なし）'}",
            f"推奨アクション: {actions or '（なし）'}",
            "",
        ]

    if one_week:
        _extract(one_week, "1週間前")
    if one_month:
        _extract(one_month, "1か月前")

    lines += [
        f"現在の総資産額: {format_jpy(current_total)}",
        "---",
        "上記の過去推奨を踏まえ、その後どうなったかを `lookback_review` フィールドで自己採点してください。",
    ]
    return "\n".join(lines)


def _rich_text(props: dict[str, Any], key: str, *, title: bool = False) -> str:
    prop = props.get(key) or {}
    parts = prop.get("title" if title else "rich_text") or []
    return "".join(p.get("plain_text", "") for p in parts)
