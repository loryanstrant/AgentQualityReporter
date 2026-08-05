"""Health endpoint smoke test."""
import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] is True
    assert body["status"] == "ok"
