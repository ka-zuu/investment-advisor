"""エージェント実行（Step 11-14）。ペルソナ4体→議長の2段階実行。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

from investment_advisor import config
from investment_advisor.agents import prompts as _prompts
from investment_advisor.agents.llm_adapter import LLMResponse, make_adapter
from investment_advisor.notion_client import NotionClient
from investment_advisor.utils.logging import estimate_cost_usd

if TYPE_CHECKING:
    from investment_advisor.portfolio.models import PortfolioSummary


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    agent_name: str
    agent_page_id: str
    overall_rating: str
    score: int
    summary: str
    detail: str
    actions: str
    follow_up: str
    is_synthesizer: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    provider: str = ""
    # 議長専用フィールド
    opinion_conflict: str = ""
    weekly_checks: str = ""
    action_immediate: str = ""
    action_consider: str = ""
    action_skip: str = ""


@dataclass
class ExecutionStats:
    runs: list[dict[str, Any]] = field(default_factory=list)

    def record(
        self, agent: str, provider: str, model: str, input_tokens: int, output_tokens: int
    ) -> None:
        self.runs.append(
            {
                "agent": agent,
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
        )

    def total_cost_usd(self) -> float:
        return sum(estimate_cost_usd(r["model"], r["input_tokens"], r["output_tokens"]) for r in self.runs)


# ---------------------------------------------------------------------------
# ツール定義（構造化出力に tool_choice=any / FunctionCallingConfig.ANY を使用）
# ---------------------------------------------------------------------------

_PERSONA_TOOL: dict[str, Any] = {
    "name": "submit_analysis",
    "description": "ポートフォリオの分析結果を構造化して提出する",
    "input_schema": {
        "type": "object",
        "properties": {
            "overall_rating": {
                "type": "string",
                "enum": ["良好", "注意", "警戒"],
                "description": "総合評価",
            },
            "score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "ポートフォリオ健全性スコア（0〜100）",
            },
            "summary": {"type": "string", "description": "短い結論（2〜3文）"},
            "detail": {
                "type": "string",
                "description": "詳細分析。根拠・不確実性・反対意見を必ず含める。投資判断を断定しない。",
            },
            "actions": {"type": "string", "description": "推奨アクション（箇条書き）"},
            "follow_up": {"type": "string", "description": "要確認事項（箇条書き）"},
        },
        "required": ["overall_rating", "score", "summary", "detail", "actions", "follow_up"],
    },
}

_SYNTHESIZER_TOOL: dict[str, Any] = {
    "name": "submit_synthesis",
    "description": "4エージェントの分析を統合した議長としての結論を提出する",
    "input_schema": {
        "type": "object",
        "properties": {
            "overall_rating": {
                "type": "string",
                "enum": ["良好", "注意", "警戒"],
                "description": "全体総合評価",
            },
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "summary": {"type": "string", "description": "議長としての全体サマリ（3〜5文）"},
            "weekly_checks": {"type": "string", "description": "今週の確認事項（箇条書き）"},
            "action_immediate": {"type": "string", "description": "すぐやる（箇条書き）"},
            "action_consider": {"type": "string", "description": "検討する（箇条書き）"},
            "action_skip": {"type": "string", "description": "見送る（理由付き箇条書き）"},
        },
        "required": [
            "overall_rating", "score", "summary",
            "weekly_checks", "action_immediate", "action_consider", "action_skip",
        ],
    },
}


# ---------------------------------------------------------------------------
# パブリック API
# ---------------------------------------------------------------------------


def run_all_agents(
    client: NotionClient,
    summary: PortfolioSummary,
    holdings: list[dict[str, Any]],
    report_page_id: str,
    ref_date: date,
) -> tuple[list[AgentResult], AgentResult | None, ExecutionStats]:
    """Step 11-14: ペルソナ4体を実行し、その後議長を実行する。"""
    stats = ExecutionStats()
    policy = _prompts.load_investment_policy(client)
    portfolio_ctx = _prompts.build_portfolio_context(summary, holdings, policy)

    agents = _load_active_agents(client)
    persona_agents = [a for a in agents if not _is_synthesizer(a)]
    synth_agents = [a for a in agents if _is_synthesizer(a)]

    adapter = make_adapter()

    persona_results: list[AgentResult] = []
    for agent_page in persona_agents:
        result = _run_persona(adapter, client, agent_page, portfolio_ctx, report_page_id, ref_date, stats)
        if result:
            persona_results.append(result)

    synth_result: AgentResult | None = None
    if synth_agents and persona_results:
        synth_ctx = _prompts.build_synthesizer_context(persona_results)
        synth_result = _run_synthesizer(
            adapter, client, synth_agents[0], portfolio_ctx, synth_ctx, report_page_id, ref_date, stats
        )

    return persona_results, synth_result, stats


# ---------------------------------------------------------------------------
# 内部実装
# ---------------------------------------------------------------------------


def _load_active_agents(client: NotionClient) -> list[dict[str, Any]]:
    return client.query_database(
        config.NOTION_DB_AGENT,
        filter={"property": "有効", "checkbox": {"equals": True}},
        sorts=[{"property": "優先度", "direction": "ascending"}],
    )


def _is_synthesizer(agent_page: dict[str, Any]) -> bool:
    name = _agent_name(agent_page)
    return "議長" in name or "Synthesizer" in name or "統合" in name


def _agent_name(agent_page: dict[str, Any]) -> str:
    props = agent_page["properties"]
    parts = (props.get("エージェント名") or {}).get("title") or []
    return "".join(p.get("plain_text", "") for p in parts)


def _agent_prompt(agent_page: dict[str, Any]) -> str:
    props = agent_page["properties"]
    parts = (props.get("プロンプト") or {}).get("rich_text") or []
    return "".join(p.get("plain_text", "") for p in parts)


def _run_persona(
    adapter: Any,
    client: NotionClient,
    agent_page: dict[str, Any],
    portfolio_ctx: str,
    report_page_id: str,
    ref_date: date,
    stats: ExecutionStats,
) -> AgentResult | None:
    name = _agent_name(agent_page)
    system = _agent_prompt(agent_page) or f"あなたは投資ポートフォリオ分析エージェントです。エージェント名: {name}"
    print(f"[runner] {name} 実行中... (provider={config.LLM_PROVIDER}, model={config.LLM_MODEL_PERSONA})")
    try:
        resp: LLMResponse = adapter.complete_with_tool(
            model=config.LLM_MODEL_PERSONA,
            max_tokens=1500,
            system=system,
            user_content=portfolio_ctx,
            tool=_PERSONA_TOOL,
        )
    except Exception as e:
        print(f"[runner] {name} エラー: {e}")
        return None

    stats.record(name, config.LLM_PROVIDER, config.LLM_MODEL_PERSONA, resp.input_tokens, resp.output_tokens)

    if not resp.tool_input:
        print(f"[runner] {name}: tool呼び出しなし、スキップ")
        return None

    data = resp.tool_input
    result = AgentResult(
        agent_name=name,
        agent_page_id=agent_page["id"],
        overall_rating=data.get("overall_rating", "注意"),
        score=int(data.get("score", 50)),
        summary=data.get("summary", ""),
        detail=data.get("detail", ""),
        actions=data.get("actions", ""),
        follow_up=data.get("follow_up", ""),
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
        model=config.LLM_MODEL_PERSONA,
        provider=config.LLM_PROVIDER,
    )
    # P1: Agent Analysis Results DB への保存
    _save_analysis_result_if_enabled(client, result, report_page_id, ref_date)
    return result


def _run_synthesizer(
    adapter: Any,
    client: NotionClient,
    agent_page: dict[str, Any],
    portfolio_ctx: str,
    synth_ctx: str,
    report_page_id: str,
    ref_date: date,
    stats: ExecutionStats,
) -> AgentResult | None:
    name = _agent_name(agent_page)
    system = (
        _agent_prompt(agent_page)
        or "あなたは投資委員会の議長です。4つのエージェントの分析を統合し、今週の確認事項と最終アクション候補を整理してください。投資判断を断定せず、最終判断はユーザーが行う前提で書いてください。"
    )
    print(f"[runner] {name}（議長）実行中... (provider={config.LLM_PROVIDER}, model={config.LLM_MODEL_SYNTHESIZER})")
    user_content = f"{portfolio_ctx}\n\n{synth_ctx}"
    try:
        resp: LLMResponse = adapter.complete_with_tool(
            model=config.LLM_MODEL_SYNTHESIZER,
            max_tokens=3000,
            system=system,
            user_content=user_content,
            tool=_SYNTHESIZER_TOOL,
        )
    except Exception as e:
        print(f"[runner] {name} エラー: {e}")
        return None

    stats.record(name, config.LLM_PROVIDER, config.LLM_MODEL_SYNTHESIZER, resp.input_tokens, resp.output_tokens)

    if not resp.tool_input:
        return None

    data = resp.tool_input
    result = AgentResult(
        agent_name=name,
        agent_page_id=agent_page["id"],
        overall_rating=data.get("overall_rating", "注意"),
        score=int(data.get("score", 50)),
        summary=data.get("summary", ""),
        detail="",
        actions=data.get("action_immediate", ""),
        follow_up=data.get("weekly_checks", ""),
        is_synthesizer=True,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
        model=config.LLM_MODEL_SYNTHESIZER,
        provider=config.LLM_PROVIDER,
        weekly_checks=data.get("weekly_checks", ""),
        action_immediate=data.get("action_immediate", ""),
        action_consider=data.get("action_consider", ""),
        action_skip=data.get("action_skip", ""),
    )
    # P1: Agent Analysis Results DB への保存
    _save_analysis_result_if_enabled(client, result, report_page_id, ref_date)
    return result


def _save_analysis_result_if_enabled(
    client: NotionClient,
    result: AgentResult,
    report_page_id: str,
    ref_date: date,
) -> None:
    """P1: NOTION_DB_AGENT_ANALYSIS が設定されている場合のみ保存する。"""
    if not config.NOTION_DB_AGENT_ANALYSIS:
        return

    props: dict[str, Any] = {
        "分析名": {"title": [{"text": {"content": f"{result.agent_name} {ref_date}"}}]},
        "日付": {"date": {"start": ref_date.isoformat()}},
        "総合評価": {"select": {"name": result.overall_rating}},
        "スコア": {"number": result.score},
        "要約": {"rich_text": [{"text": {"content": result.summary[:2000]}}]},
        "詳細分析": {"rich_text": [{"text": {"content": result.detail[:2000]}}]},
        "推奨アクション": {"rich_text": [{"text": {"content": result.actions[:2000]}}]},
        "要確認事項": {"rich_text": [{"text": {"content": result.follow_up[:2000]}}]},
        "エージェント": {"relation": [{"id": result.agent_page_id}]},
    }
    if report_page_id:
        props["対象レポート"] = {"relation": [{"id": report_page_id}]}

    try:
        client.create_page(config.NOTION_DB_AGENT_ANALYSIS, props)
        print(f"[runner] {result.agent_name} 分析結果保存完了 (P1)")
    except Exception as e:
        print(f"[runner] {result.agent_name} 分析結果保存エラー（スキップ）: {e}")
