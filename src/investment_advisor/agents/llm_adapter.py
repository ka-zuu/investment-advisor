"""LLMプロバイダー抽象化レイヤー。Gemini / Claude を設定で切り替える。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from investment_advisor import config


@dataclass
class LLMResponse:
    tool_input: dict[str, Any] | None
    input_tokens: int
    output_tokens: int


def make_adapter() -> "_BaseAdapter":
    provider = config.LLM_PROVIDER.lower()
    if provider == "gemini":
        return _GeminiAdapter()
    if provider == "claude":
        return _ClaudeAdapter()
    raise ValueError(f"不明なLLMプロバイダー: {provider}  (LLM_PROVIDER=gemini または claude を設定してください)")


class _BaseAdapter:
    def complete_with_tool(
        self,
        model: str,
        max_tokens: int,
        system: str,
        user_content: str,
        tool: dict[str, Any],
    ) -> LLMResponse:
        raise NotImplementedError


class _GeminiAdapter(_BaseAdapter):
    def complete_with_tool(
        self,
        model: str,
        max_tokens: int,
        system: str,
        user_content: str,
        tool: dict[str, Any],
    ) -> LLMResponse:
        import time

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=config.GOOGLE_API_KEY)

        func_decl = types.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters=tool["input_schema"],
        )
        gen_config = types.GenerateContentConfig(
            tools=[types.Tool(function_declarations=[func_decl])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="ANY")
            ),
            max_output_tokens=max_tokens,
            system_instruction=system,
        )

        for attempt in range(4):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=user_content,
                    config=gen_config,
                )
            except Exception as e:
                if attempt < 3 and "503" in str(e):
                    wait = 15 * (2 ** attempt)
                    print(f"[llm_adapter] 503 一時的エラー、{wait}秒後にリトライ ({attempt + 1}/3)...")
                    time.sleep(wait)
                    continue
                raise

            in_tok = getattr(resp.usage_metadata, "prompt_token_count", 0) or 0
            out_tok = getattr(resp.usage_metadata, "candidates_token_count", 0) or 0

            for part in resp.candidates[0].content.parts:
                if part.function_call:
                    return LLMResponse(
                        tool_input=dict(part.function_call.args),
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                    )

            return LLMResponse(tool_input=None, input_tokens=in_tok, output_tokens=out_tok)

        raise RuntimeError(f"Gemini API が {model} で連続して503を返しました")


class _ClaudeAdapter(_BaseAdapter):
    def complete_with_tool(
        self,
        model: str,
        max_tokens: int,
        system: str,
        user_content: str,
        tool: dict[str, Any],
    ) -> LLMResponse:
        import anthropic

        api = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = api.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": user_content}],
        )

        for block in resp.content:
            if block.type == "tool_use":
                return LLMResponse(
                    tool_input=block.input,  # type: ignore[arg-type]
                    input_tokens=resp.usage.input_tokens,
                    output_tokens=resp.usage.output_tokens,
                )

        return LLMResponse(
            tool_input=None,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )
