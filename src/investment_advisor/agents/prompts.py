from __future__ import annotations

from typing import TYPE_CHECKING, Any

from investment_advisor import config
from investment_advisor.notion_client import NotionClient
from investment_advisor.portfolio.models import PortfolioSummary
from investment_advisor.utils.money import format_jpy, format_pct

if TYPE_CHECKING:
    from investment_advisor.agents.runner import AgentResult


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
        name = _rich_text(props, "資産名", title=True)
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

    if policy:
        lines += ["", "## 投資方針"]
        for k, v in policy.items():
            if v:
                lines.append(f"- {k}: {v}")

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
    return "\n".join(lines)


def _rich_text(props: dict[str, Any], key: str, *, title: bool = False) -> str:
    prop = props.get(key) or {}
    parts = prop.get("title" if title else "rich_text") or []
    return "".join(p.get("plain_text", "") for p in parts)
