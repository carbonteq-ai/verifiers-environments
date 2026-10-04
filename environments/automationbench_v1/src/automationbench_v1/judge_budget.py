"""Exact server-side chat token budgeting for a local vLLM episode judge."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


class JudgeBudgetError(ValueError):
    """An episode cannot be judged within the selected context contract."""


def _tokenize_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path.rstrip("/") != "/v1":
        raise JudgeBudgetError("vLLM judge budgeting requires a base_url ending in /v1")
    return urlunsplit((parsed.scheme, parsed.netloc, "/tokenize", "", ""))


async def measure_vllm_chat_tokens(
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    api_key: str,
    headers: dict[str, str],
    chat_template_kwargs: dict[str, Any] | None,
) -> tuple[int, int]:
    """Use the serving renderer, not a possibly different local tokenizer."""

    request = {"model": model, "messages": messages, "add_generation_prompt": True}
    if chat_template_kwargs:
        request["chat_template_kwargs"] = chat_template_kwargs
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            _tokenize_url(base_url),
            json=request,
            headers={**headers, "Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        payload = response.json()
    count, max_model_len = payload.get("count"), payload.get("max_model_len")
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count < 1
        or isinstance(max_model_len, bool)
        or not isinstance(max_model_len, int)
        or max_model_len < 1
    ):
        raise JudgeBudgetError("vLLM /tokenize returned invalid token-count metadata")
    return count, max_model_len


def admitted_output_tokens(
    *,
    input_tokens: int,
    server_context_tokens: int,
    configured_context_tokens: int,
    requested_output_tokens: int,
    safety_margin_tokens: int,
    minimum_output_tokens: int,
    initial_input_budget_tokens: int | None = None,
) -> int:
    """Fail closed on oversized inputs; otherwise fit output inside context."""

    if initial_input_budget_tokens is not None and input_tokens > initial_input_budget_tokens:
        raise JudgeBudgetError(
            f"rendered judge input has {input_tokens} tokens; budget is {initial_input_budget_tokens}"
        )
    context = min(server_context_tokens, configured_context_tokens)
    output_tokens = min(requested_output_tokens, context - input_tokens - safety_margin_tokens)
    if output_tokens < minimum_output_tokens:
        raise JudgeBudgetError(
            f"judge context has insufficient response room: input={input_tokens}, "
            f"context={context}, minimum_output={minimum_output_tokens}, margin={safety_margin_tokens}"
        )
    return output_tokens


__all__ = ["JudgeBudgetError", "admitted_output_tokens", "measure_vllm_chat_tokens"]
