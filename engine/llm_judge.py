"""LLM-as-judge for Copilot Studio agent instructions.

Calls the Azure OpenAI v1 surface of a Foundry resource using an API key. Returns
a structured JSON verdict the scorecard can render. If env vars are missing or the
call fails, returns None so the pipeline still succeeds with static-only results.

ENDPOINT NOTE
-------------
The Azure OpenAI v1 base URL looks like:

    https://<resource>.openai.azure.com/openai/v1/

The OpenAI Python SDK is pointed at this base URL with the API key supplied via the
Authorization header. The v1 surface is OpenAI-SDK-compatible: model names (e.g.
"gpt-4.1") are passed directly with no deployment-name path or api-version query
string. We use chat/completions for the judge call because it's well-tested and
supports `response_format: json_object`. If the user supplies a URL with a trailing
operation (e.g. "/responses" or "/chat/completions"), we trim it back to the base.

The same Foundry resource also exposes an AI Project endpoint
("…services.ai.azure.com/api/projects/<project>") used for Responses, Agents, and
evaluation threads — not needed for the MVP but documented for v2.
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment, misc]


JUDGE_SYSTEM_PROMPT = """You are an expert reviewer of Microsoft Copilot Studio agents.
You are reviewing one agent's configuration against the "Patterns & Practices for
Copilot Studio agent development" reference (April 2026).

Score the agent against these rubrics, citing evidence from the supplied text:

1. clarity (0-5): Are the instructions clear, well-structured, and free of ambiguity?
2. persona_defined (boolean): Do the instructions establish a role/persona for the agent?
3. scope_discipline (0-5): Do the instructions tell the agent what it should AND should
   not do, and how to behave on out-of-scope requests?
4. orchestrator_pattern_detected (boolean): Do the instructions match the
   orchestrator pattern (decompose requests, route deliberately, combine responses,
   never expose raw child responses)?
5. child_pattern_detected (boolean): Do the instructions match the connected/child
   agent pattern (strict scope, respond "Not applicable for this request" when off-scope)?
6. output_format_guidance (boolean): Do the instructions specify response format,
   tone, or structure?

Also return:
- top_strengths: up to 3 specific strengths, quoting evidence where possible.
- top_weaknesses: up to 3 specific weaknesses with actionable fixes.
- recommended_changes: up to 5 concrete, prioritised changes.

Be strict. Empty or generic instructions score low. Boilerplate without
specifics scores low. Only one of orchestrator_pattern_detected and
child_pattern_detected should typically be true, but both can be false if the agent
is a single standalone agent.

Respond with valid JSON matching this schema exactly:
{
  "clarity": int,
  "persona_defined": bool,
  "scope_discipline": int,
  "orchestrator_pattern_detected": bool,
  "child_pattern_detected": bool,
  "output_format_guidance": bool,
  "top_strengths": [str],
  "top_weaknesses": [str],
  "recommended_changes": [str],
  "summary": str
}"""


def judge_available(
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> bool:
    base_url = base_url or os.environ.get("AZURE_OPENAI_BASE_URL")
    model = model or os.environ.get("AZURE_OPENAI_MODEL")
    api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
    return bool(OpenAI and base_url and model and api_key)


def _normalise_base_url(raw: str) -> str:
    """Strip trailing operation suffixes so we have just the v1 base.

    Accepts inputs such as:
        https://x.services.ai.azure.com/api/projects/P/openai/v1
        https://x.services.ai.azure.com/api/projects/P/openai/v1/
        https://x.services.ai.azure.com/api/projects/P/openai/v1/responses
        https://x.services.ai.azure.com/api/projects/P/openai/v1/chat/completions
    """
    url = raw.rstrip("/")
    for suffix in ("/responses", "/chat/completions", "/completions", "/embeddings"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    if not url.endswith("/"):
        url += "/"
    return url


def judge_agent(
    bot: dict[str, Any],
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any] | None:
    """Score a single agent. Returns dict on success, None on failure/skip.

    Config is taken from the supplied arguments (the admin-stored Foundry
    settings) when present, otherwise from the AZURE_OPENAI_* environment vars.
    """
    base_url = base_url or os.environ.get("AZURE_OPENAI_BASE_URL")
    model = model or os.environ.get("AZURE_OPENAI_MODEL")
    api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
    if not judge_available(base_url, model, api_key):
        return None

    text = bot.get("raw_text_for_judge") or ""
    if not text.strip():
        return {
            "skipped": True,
            "reason": "No instruction text was extracted from the bot export.",
        }

    user_payload = {
        "display_name": bot.get("display_name"),
        "description": bot.get("description"),
        "topics": bot.get("topics", []),
        "model": bot.get("model"),
        "instruction_text": text,
    }

    client = OpenAI(
        base_url=_normalise_base_url(base_url),
        api_key=api_key,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=1500,
        )
        raw = response.choices[0].message.content or "{}"
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
