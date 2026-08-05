"""FastAPI application entrypoint.

Exposes ``/health``, mounts the auth/admin/reports routers, serves the built SPA
in production, runs migrations + admin seeding on startup, and — on a brand-new
database — runs one bundled demo scan so the dashboard has data to show.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from shared.config import settings
from shared.db import engine
from shared.version import APP_VERSION

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("api")


async def _seed_admin_from_env() -> None:
    if not (settings.admin_username and settings.admin_password):
        return
    from sqlalchemy import func, select

    from shared.db import SessionLocal
    from shared.models import AppUser
    from shared.security import hash_password

    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(AppUser))
        if count:
            return
        session.add(
            AppUser(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                role="admin",
            )
        )
        await session.commit()
        logger.info("Seeded initial admin user '%s'.", settings.admin_username)


async def _seed_demo_scan() -> None:
    """Deprecated: demo environment removed. Retained as a no-op for safety."""
    return


async def _seed_rule_configs() -> None:
    """Seed the editable rule-config table from the markdown catalogue."""
    from shared.db import SessionLocal
    from shared.rules_config import sync_rule_configs

    async with SessionLocal() as session:
        await sync_rule_configs(session)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("RUN_MIGRATIONS_ON_STARTUP", "true").lower() != "false":
        try:
            from shared.migrate import upgrade_to_head

            upgrade_to_head()
        except Exception as exc:  # pragma: no cover - startup diagnostics
            logger.error("Migration on startup failed: %s", exc)
    try:
        await _seed_admin_from_env()
        await _seed_rule_configs()
    except Exception as exc:  # pragma: no cover - startup diagnostics
        logger.error("Startup seeding failed: %s", exc)
    yield


app = FastAPI(
    title="Copilot Studio Agent Quality Platform",
    version=APP_VERSION,
    description="Live-API quality scanning for Copilot Studio agents with a web dashboard.",
    lifespan=lifespan,
)


@app.get("/health", tags=["system"])
async def health() -> JSONResponse:
    db_ok = False
    detail = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # pragma: no cover
        detail = f"database unavailable: {exc}"
        logger.warning("Health check failed: %s", detail)

    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={
            "status": "ok" if db_ok else "degraded",
            "database": db_ok,
            "environment": settings.app_env,
            "detail": detail,
        },
    )


def _register_routers() -> None:
    from api.routers import admin, auth, reports

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(reports.router)


_register_routers()


def _mount_frontend() -> None:
    dist = settings.frontend_dist
    index_path = os.path.join(dist, "index.html")
    if not os.path.isfile(index_path):
        logger.info("Frontend bundle not found at %s (dev mode)", dist)
        return

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    assets_dir = os.path.join(dist, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        candidate = os.path.join(dist, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(index_path)

    logger.info("Serving frontend bundle from %s", dist)


_mount_frontend()
