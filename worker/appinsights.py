"""Application Insights query client (agent telemetry evidence for AGT-007).

Uses the Application Insights REST query API:
    GET https://api.applicationinsights.io/v1/apps/{appId}/query?query=<KQL>
with an ``x-api-key`` header. Returns run/error/latency figures for an agent over
a trailing window. All failures degrade gracefully to ``None`` so a missing or
misconfigured workspace never fails a scan.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("worker.appinsights")

_BASE = "https://api.applicationinsights.io/v1/apps"
_TIMEOUT = 30.0


async def fetch_agent_telemetry(
    *,
    app_id: str,
    api_key: str,
    agent_name: str,
    window_days: int = 30,
) -> dict[str, Any] | None:
    """Return {run_count, error_count, p95_latency_ms, window_days} or None."""
    if not (app_id and api_key):
        return None
    # Copilot Studio emits custom events; we approximate volume/errors/latency.
    kql = (
        "let win = {days}d;"
        "let name = '{name}';"
        "union customEvents, requests, dependencies "
        "| where timestamp > ago(win) "
        "| where tostring(customDimensions.botName) == name "
        "   or tostring(cloud_RoleName) == name "
        "| summarize runs = count(), "
        "   errors = countif(success == false), "
        "   p95 = percentile(duration, 95)"
    ).format(days=window_days, name=agent_name.replace("'", "''"))

    headers = {"x-api-key": api_key, "Accept": "application/json"}
    url = f"{_BASE}/{app_id}/query"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params={"query": kql}, headers=headers)
        if resp.status_code >= 400:
            logger.info("App Insights query failed (%s): %s", resp.status_code, resp.text[:200])
            return None
        tables = resp.json().get("tables") or []
        if not tables or not tables[0].get("rows"):
            return {"run_count": 0, "error_count": 0, "p95_latency_ms": None, "window_days": window_days}
        cols = [c["name"] for c in tables[0]["columns"]]
        row = tables[0]["rows"][0]
        record = dict(zip(cols, row))
        return {
            "run_count": int(record.get("runs") or 0),
            "error_count": int(record.get("errors") or 0),
            "p95_latency_ms": float(record["p95"]) if record.get("p95") is not None else None,
            "window_days": window_days,
        }
    except Exception as exc:  # noqa: BLE001
        logger.info("App Insights telemetry unavailable for %s: %s", agent_name, exc)
        return None
