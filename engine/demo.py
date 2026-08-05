"""Bundled demo dataset (per-agent shape).

Produces the same ``{"agents": [...], "default_icon_hash": ...}`` structure the live
Dataverse collector emits, so the platform can be demonstrated end-to-end without a
live connection. ``source: demo`` behaves like a live read. Each agent carries its
own owning-solution context, so solution-level rules are scored per agent.
"""
from __future__ import annotations

from typing import Any

_GOOD_INSTRUCTIONS = (
    "You are the Contoso HR Assistant, a friendly and precise virtual colleague "
    "for Contoso employees. Your role is to help staff with leave balances, "
    "payslips, and HR policy questions. Always confirm the employee's intent "
    "before taking action, and decompose multi-part requests into discrete steps: "
    "identify the employee, retrieve the relevant record, then summarise the answer "
    "in plain language. If a request is outside HR scope (IT, finance, facilities), "
    "politely say it is not something you can help with and point the user to the "
    "correct team. Never expose raw system responses; always format results as a "
    "short summary followed by a bulleted breakdown. Maintain a warm, professional "
    "tone and never speculate about an employee's personal circumstances."
)


def demo_environment() -> dict[str, Any]:
    good = {
        "source": "demo",
        "bot_id": "11111111-1111-1111-1111-111111111111",
        "folder": "contoso_hrAssistant",
        "schema_name": "contoso_hrAssistant",
        "display_name": "Contoso HR Assistant",
        "description": (
            "Helps Contoso employees with leave balances, payslips and HR policy "
            "questions, routing anything out of scope to the right team."
        ),
        "instructions": _GOOD_INSTRUCTIONS,
        "raw_text_for_judge": _GOOD_INSTRUCTIONS,
        "model": "GPT41",
        "topics": ["Leave Balance", "Payslip", "Greeting", "Fallback"],
        "user_topics": ["Leave Balance", "Payslip"],
        "system_topics": ["Greeting", "Fallback"],
        "modified_system_topics": [],
        "suggested_prompts": [
            "How much annual leave do I have left?",
            "Show my latest payslip",
            "What is the parental leave policy?",
        ],
        "telemetry_app_insights_key": "InstrumentationKey=demo-hr",
        "telemetry": {"run_count": 1240, "error_count": 12, "p95_latency_ms": 820.0, "window_days": 30},
        "icon_present": True,
        "icon_hash": "cafebabe" * 8,
        "icon_is_custom": True,
        "publish_state": "published",
        "published": True,
        "solution": {
            "found": True,
            "unique_name": "ContosoHR",
            "display_name": "Contoso HR",
            "version": "1.4.2.0",
            "publisher_prefix": "contoso",
            "publisher_name": "ContosoPublisher",
            "is_default": False,
        },
        "connection_references": [
            {"logical_name": "contoso_sharedoffice365"},
            {"logical_name": "contoso_sharedcommondataservice"},
        ],
        "environment_variables": [
            {"schema_name": "contoso_HrApiBaseUrl"},
            {"schema_name": "contoso_TenantRegion"},
        ],
    }
    poor = {
        "source": "demo",
        "bot_id": "22222222-2222-2222-2222-222222222222",
        "folder": "contoso_testBot",
        "schema_name": "contoso_testBot",
        "display_name": "Test Bot",
        "description": "",
        "instructions": "You help.",
        "raw_text_for_judge": "You help.",
        "model": "GPT4o",
        "topics": ["Greeting", "Fallback", "Escalate"],
        "user_topics": [],
        "system_topics": ["Greeting", "Fallback", "Escalate"],
        "modified_system_topics": [],
        "suggested_prompts": [],
        "telemetry_app_insights_key": None,
        "telemetry": {},
        "icon_present": True,
        "icon_hash": "de1a0117" * 8,
        "icon_is_custom": False,
        "publish_state": "draft",
        "published": False,
        "solution": {
            "found": False,
            "unique_name": None,
            "version": None,
            "publisher_prefix": None,
            "publisher_name": None,
            "is_default": True,
        },
        "connection_references": [],
        "environment_variables": [],
    }
    return {"agents": [good, poor], "default_icon_hash": "de1a0117" * 8}
