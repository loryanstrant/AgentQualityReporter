"""Admin routes (admin role required).

Configure the service-principal + Foundry credentials, manage environments to
scan, seed default-icon hashes, test connectivity, and trigger scans.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import CurrentUser, require_admin
from api.schemas import (
    AppConfigIn,
    AppConfigOut,
    EnvironmentIn,
    EnvironmentOut,
    RuleConfigIn,
    ScanRunOut,
    StatusOut,
    ScanSummaryOut,
    TestConnectionOut,
)
from shared.crypto import decrypt, encrypt
from shared.db import SessionLocal, get_session
from shared.models import Agent, AppConfig, Environment, RuleConfig, Scan
from shared.rules_config import sync_rule_configs
from worker.scan import ScanError, run_scan

logger = logging.getLogger("api.admin")

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

_scan_lock = asyncio.Lock()


def _cfg_out(cfg: AppConfig | None) -> AppConfigOut:
    if cfg is None:
        return AppConfigOut()
    return AppConfigOut(
        tenant_id=cfg.tenant_id,
        client_id=cfg.client_id,
        has_client_secret=bool(cfg.client_secret_encrypted),
        aoai_base_url=cfg.aoai_base_url,
        aoai_model=cfg.aoai_model,
        has_aoai_key=bool(cfg.aoai_key_encrypted),
        report_access_group_id=cfg.report_access_group_id,
        schedule_interval_hours=cfg.schedule_interval_hours or 24,
        default_icon_hashes=list(cfg.default_icon_hashes or []),
        configured=bool(cfg.tenant_id and cfg.client_id and cfg.client_secret_encrypted),
        judge_configured=bool(cfg.aoai_base_url and cfg.aoai_model and cfg.aoai_key_encrypted),
        updated_at=cfg.updated_at,
        updated_by=cfg.updated_by,
    )


@router.get("/config", response_model=AppConfigOut)
async def get_config(session: AsyncSession = Depends(get_session)) -> AppConfigOut:
    return _cfg_out(await session.get(AppConfig, 1))


@router.put("/config", response_model=AppConfigOut)
async def put_config(
    body: AppConfigIn,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AppConfigOut:
    cfg = await session.get(AppConfig, 1)
    if cfg is None:
        cfg = AppConfig(id=1)
        session.add(cfg)

    if body.tenant_id is not None:
        cfg.tenant_id = body.tenant_id.strip() or None
    if body.client_id is not None:
        cfg.client_id = body.client_id.strip() or None
    if body.client_secret:
        cfg.client_secret_encrypted = encrypt(body.client_secret)
    if body.aoai_base_url is not None:
        cfg.aoai_base_url = body.aoai_base_url.strip() or None
    if body.aoai_model is not None:
        cfg.aoai_model = body.aoai_model.strip() or None
    if body.aoai_key:
        cfg.aoai_key_encrypted = encrypt(body.aoai_key)
    if body.report_access_group_id is not None:
        cfg.report_access_group_id = body.report_access_group_id.strip() or None
    if body.schedule_interval_hours is not None:
        cfg.schedule_interval_hours = max(1, min(body.schedule_interval_hours, 24))
    if body.default_icon_hashes is not None:
        cfg.default_icon_hashes = [h.strip().lower() for h in body.default_icon_hashes if h.strip()]
    cfg.updated_by = user.username

    await session.commit()
    await session.refresh(cfg)
    return _cfg_out(cfg)


@router.post("/test-connection", response_model=TestConnectionOut)
async def test_connection(
    environment_id: int, session: AsyncSession = Depends(get_session)
) -> TestConnectionOut:
    cfg = await session.get(AppConfig, 1)
    env = await session.get(Environment, environment_id)
    if cfg is None or not (cfg.tenant_id and cfg.client_id and cfg.client_secret_encrypted):
        return TestConnectionOut(ok=False, detail="Service principal not configured.")
    if env is None or not env.dataverse_url:
        return TestConnectionOut(ok=False, detail="Environment or Dataverse URL missing.")
    from worker.dataverse import test_dataverse_connection

    result = await test_dataverse_connection(
        org_url=env.dataverse_url,
        tenant_id=cfg.tenant_id,
        client_id=cfg.client_id,
        client_secret=decrypt(cfg.client_secret_encrypted),
    )
    return TestConnectionOut(**{k: v for k, v in result.items() if k in TestConnectionOut.model_fields})


# --- environments -------------------------------------------------------
def _env_out(env: Environment) -> EnvironmentOut:
    return EnvironmentOut(
        id=env.id,
        display_name=env.display_name,
        dataverse_url=env.dataverse_url,
        app_insights_app_id=env.app_insights_app_id,
        has_app_insights_key=bool(env.app_insights_key_encrypted),
        enabled=env.enabled,
        created_at=env.created_at,
    )


@router.get("/environments", response_model=list[EnvironmentOut])
async def list_environments(session: AsyncSession = Depends(get_session)) -> list[EnvironmentOut]:
    rows = (await session.execute(select(Environment).order_by(Environment.id))).scalars().all()
    out = []
    for e in rows:
        last = await session.scalar(
            select(Scan)
            .where(Scan.environment_id == e.id, Scan.status == "complete")
            .order_by(Scan.started_at.desc())
            .limit(1)
        )
        item = _env_out(e)
        if last:
            item.last_scanned = last.finished_at or last.started_at
            item.last_agent_count = last.agent_count
        out.append(item)
    return out


@router.post("/environments", response_model=EnvironmentOut)
async def create_environment(
    body: EnvironmentIn, session: AsyncSession = Depends(get_session)
) -> EnvironmentOut:
    env = Environment(
        display_name=body.display_name,
        dataverse_url=(body.dataverse_url or "").strip() or None,
        app_insights_app_id=(body.app_insights_app_id or "").strip() or None,
        enabled=body.enabled,
    )
    if body.app_insights_key:
        env.app_insights_key_encrypted = encrypt(body.app_insights_key)
    session.add(env)
    await session.commit()
    await session.refresh(env)
    return _env_out(env)


@router.put("/environments/{env_id}", response_model=EnvironmentOut)
async def update_environment(
    env_id: int, body: EnvironmentIn, session: AsyncSession = Depends(get_session)
) -> EnvironmentOut:
    env = await session.get(Environment, env_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    env.display_name = body.display_name
    env.dataverse_url = (body.dataverse_url or "").strip() or None
    env.app_insights_app_id = (body.app_insights_app_id or "").strip() or None
    env.enabled = body.enabled
    if body.app_insights_key:
        env.app_insights_key_encrypted = encrypt(body.app_insights_key)
    await session.commit()
    await session.refresh(env)
    return _env_out(env)


@router.delete("/environments/{env_id}")
async def delete_environment(env_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    env = await session.get(Environment, env_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    await session.delete(env)
    await session.commit()
    return {"status": "deleted", "id": env_id}


# --- scans --------------------------------------------------------------
async def _do_scan(source: str, environment_id: int | None) -> None:
    async with _scan_lock:
        try:
            await run_scan(
                SessionLocal, source=source, environment_id=environment_id, trigger="manual"
            )
        except Exception:  # noqa: BLE001 - surfaced via scan.status = failed
            logger.exception("Background scan failed")


@router.post("/scan/run", response_model=ScanRunOut)
async def scan_run(
    background: BackgroundTasks,
    source: str = "demo",
    environment_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> ScanRunOut:
    if _scan_lock.locked():
        return ScanRunOut(status="already_running", detail="A scan is already in progress.")
    # Validate config up front so obvious errors return synchronously.
    if source == "dataverse":
        cfg = await session.get(AppConfig, 1)
        env = await session.get(Environment, environment_id) if environment_id else None
        if cfg is None or not (cfg.tenant_id and cfg.client_id and cfg.client_secret_encrypted):
            raise HTTPException(status_code=400, detail="Service principal not configured.")
        if env is None or not env.dataverse_url:
            raise HTTPException(status_code=400, detail="Environment or Dataverse URL missing.")
    background.add_task(_do_scan, source, environment_id)
    return ScanRunOut(status="started", detail="Scan started — watch progress on the dashboard.")


@router.post("/scan/all", response_model=ScanRunOut)
async def scan_all(
    background: BackgroundTasks, session: AsyncSession = Depends(get_session)
) -> ScanRunOut:
    """Trigger a background scan for every enabled environment."""
    if _scan_lock.locked():
        return ScanRunOut(status="already_running", detail="A scan is already in progress.")
    cfg = await session.get(AppConfig, 1)
    if cfg is None or not (cfg.tenant_id and cfg.client_id and cfg.client_secret_encrypted):
        raise HTTPException(status_code=400, detail="Service principal not configured.")
    envs = (
        await session.execute(select(Environment).where(Environment.enabled.is_(True)))
    ).scalars().all()
    ids = [e.id for e in envs if e.dataverse_url]
    if not ids:
        raise HTTPException(status_code=400, detail="No enabled environments with a Dataverse URL.")
    background.add_task(_do_scan_all, ids)
    return ScanRunOut(status="started", detail=f"Scanning {len(ids)} environment(s) — watch progress on the dashboard.")


async def _do_scan_all(env_ids: list[int]) -> None:
    async with _scan_lock:
        for env_id in env_ids:
            try:
                await run_scan(SessionLocal, source="dataverse", environment_id=env_id, trigger="manual")
            except Exception:  # noqa: BLE001
                logger.exception("Scan-all failed for environment %s", env_id)


# --- rules -------------------------------------------------------------
def _rule_out(r: RuleConfig) -> dict:
    return {
        "rule_id": r.rule_id,
        "name": r.name,
        "severity": r.severity,
        "scope": r.scope,
        "pp_reference": r.pp_reference,
        "enabled": r.enabled,
        "weight": r.weight,
        "explanation": r.explanation,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        "updated_by": r.updated_by,
    }


@router.get("/rules")
async def list_rules(session: AsyncSession = Depends(get_session)) -> list[dict]:
    await sync_rule_configs(session)
    rows = (await session.execute(select(RuleConfig).order_by(RuleConfig.rule_id))).scalars().all()
    return [_rule_out(r) for r in rows]


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    body: RuleConfigIn,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await sync_rule_configs(session)
    rule = await session.get(RuleConfig, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if body.enabled is not None:
        rule.enabled = body.enabled
    if body.weight is not None:
        rule.weight = max(0, body.weight)
    if body.explanation is not None:
        rule.explanation = body.explanation
    rule.updated_by = user.username
    await session.commit()
    await session.refresh(rule)
    return _rule_out(rule)


@router.get("/about")
async def about() -> dict:
    """Version metadata for the admin footer."""
    from engine.loader import ENGINE_VERSION, catalogue_hash
    from shared.version import APP_VERSION, BUILD_DATE, BUILD_TIME

    return {
        "version": APP_VERSION,
        "engine_version": ENGINE_VERSION,
        "catalogue_hash": catalogue_hash(),
        "build_date": BUILD_DATE,
        "build_time": BUILD_TIME,
    }


@router.get("/status", response_model=StatusOut)
async def status(session: AsyncSession = Depends(get_session)) -> StatusOut:
    cfg = await session.get(AppConfig, 1)
    scans = await session.scalar(select(func.count()).select_from(Scan)) or 0
    envs = await session.scalar(select(func.count()).select_from(Environment)) or 0
    agents = await session.scalar(select(func.count()).select_from(Agent)) or 0
    last = await session.scalar(select(Scan).order_by(Scan.started_at.desc()).limit(1))
    last_out = ScanSummaryOut.model_validate(last, from_attributes=True) if last else None
    return StatusOut(
        configured=bool(cfg and cfg.tenant_id and cfg.client_id and cfg.client_secret_encrypted),
        judge_configured=bool(cfg and cfg.aoai_base_url and cfg.aoai_model and cfg.aoai_key_encrypted),
        environments=envs,
        scans=scans,
        agents=agents,
        last_scan=last_out,
    )
