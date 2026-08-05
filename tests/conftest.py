"""Pytest fixtures: an in-memory SQLite DB and an ASGI client with a JWT.

The app normally targets Postgres; tests swap in aiosqlite and create the schema
directly from the ORM metadata (no Alembic needed), mirroring the reference project.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("FERNET_KEY", "test-fernet-key")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("RUN_MIGRATIONS_ON_STARTUP", "false")
os.environ.setdefault("SEED_DEMO_SCAN", "false")
os.environ.setdefault("ADMIN_USERNAME", "")
os.environ.setdefault("ADMIN_PASSWORD", "")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from shared.db import Base, engine
import shared.models  # noqa: F401


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_token():
    from shared.db import SessionLocal
    from shared.models import AppUser
    from shared.security import hash_password

    async with SessionLocal() as session:
        session.add(
            AppUser(username="admin", password_hash=hash_password("pw"), role="admin")
        )
        await session.commit()

    from api.auth import create_access_token

    return create_access_token("admin", "admin")
