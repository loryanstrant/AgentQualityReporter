"""Auth flow tests."""
import pytest

from shared.db import SessionLocal
from shared.models import AppUser
from shared.security import hash_password


@pytest.mark.asyncio
async def test_login_and_me(client):
    async with SessionLocal() as session:
        session.add(AppUser(username="bob", password_hash=hash_password("secret"), role="admin"))
        await session.commit()

    resp = await client.post("/auth/login", json={"username": "bob", "password": "secret"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "bob"
    assert me.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_login_rejects_bad_password(client):
    async with SessionLocal() as session:
        session.add(AppUser(username="ann", password_hash=hash_password("right"), role="viewer"))
        await session.commit()
    resp = await client.post("/auth/login", json={"username": "ann", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_route_requires_admin(client):
    async with SessionLocal() as session:
        session.add(AppUser(username="val", password_hash=hash_password("pw"), role="viewer"))
        await session.commit()
    login = await client.post("/auth/login", json={"username": "val", "password": "pw"})
    token = login.json()["access_token"]
    resp = await client.get("/admin/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
