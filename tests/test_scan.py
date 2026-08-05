"""End-to-end: run a demo scan, then read it back through the agent-first API."""
import pytest

from shared.db import SessionLocal
from worker.scan import run_scan


@pytest.mark.asyncio
async def test_demo_scan_and_agent_api(client, admin_token):
    summary = await run_scan(SessionLocal, source="demo", trigger="manual")
    assert summary["agent_count"] == 2
    # Rollup = average of the two agent scores (100 and 61).
    assert summary["score"] == 80
    scan_id = summary["scan_id"]

    headers = {"Authorization": f"Bearer {admin_token}"}

    # Demo scans are intentionally hidden from the environments list.
    envs = (await client.get("/reports/environments", headers=headers)).json()
    assert all(e["environment_id"] is not None for e in envs)

    agents = (await client.get(f"/reports/agents?scan_id={scan_id}", headers=headers)).json()
    assert len(agents) == 2
    by_name = {a["agent_name"]: a for a in agents}
    assert by_name["Contoso HR Assistant"]["grade"] == "A"
    assert by_name["Test Bot"]["grade"] == "C"

    bot_id = by_name["Test Bot"]["bot_id"]
    detail = (await client.get(f"/reports/agents/{bot_id}?scan_id={scan_id}", headers=headers)).json()
    assert detail["score"] == 61
    assert len(detail["findings"]) > 0

    hist = (await client.get(f"/reports/agents/{bot_id}/history", headers=headers)).json()
    assert len(hist) >= 1


@pytest.mark.asyncio
async def test_reports_require_auth(client):
    resp = await client.get("/reports/environments")
    assert resp.status_code == 401
