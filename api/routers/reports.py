"""Report routes (any authenticated user) — agent-first.

The dashboard is organised around agents: pick an environment, see every agent
with its own score/grade, click an agent for its findings + explanations + LLM
judge + telemetry, and view that agent's daily score history.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from shared.db import get_session
from shared.models import (
    Agent,
    AgentScore,
    Environment,
    Finding,
    JudgeResult,
    Scan,
    TelemetrySnapshot,
)

router = APIRouter(
    prefix="/reports", tags=["reports"], dependencies=[Depends(get_current_user)]
)


async def _latest_scan_per_env(session: AsyncSession) -> dict[int | None, Scan]:
    """Most recent complete scan for each real environment (demo excluded)."""
    scans = (
        await session.execute(
            select(Scan)
            .where(Scan.status == "complete", Scan.environment_id.isnot(None))
            .order_by(Scan.started_at.desc())
        )
    ).scalars().all()
    latest: dict[int | None, Scan] = {}
    for s in scans:
        if s.environment_id not in latest:
            latest[s.environment_id] = s
    return latest


@router.get("/about")
async def about() -> dict:
    """App version metadata for the About page (any authenticated user)."""
    from engine.loader import ENGINE_VERSION, catalogue_hash
    from shared.version import APP_VERSION, BUILD_DATE, BUILD_TIME

    return {
        "version": APP_VERSION,
        "engine_version": ENGINE_VERSION,
        "catalogue_hash": catalogue_hash(),
        "build_date": BUILD_DATE,
        "build_time": BUILD_TIME,
    }


@router.get("/environments")
async def environments(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """One card per environment that has been scanned, with a rollup + latest scan."""
    latest = await _latest_scan_per_env(session)
    env_rows = {
        e.id: e
        for e in (await session.execute(select(Environment))).scalars().all()
    }
    out = []
    for env_id, scan in latest.items():
        name = "Demo (bundled)" if env_id is None else (
            env_rows[env_id].display_name if env_id in env_rows else f"Environment {env_id}"
        )
        out.append({
            "environment_id": env_id,
            "name": name,
            "latest_scan_id": scan.id,
            "agent_count": scan.agent_count,
            "avg_score": scan.score,
            "grade": scan.grade,
            "scanned_at": scan.finished_at.isoformat() if scan.finished_at else None,
        })
    out.sort(key=lambda x: (x["environment_id"] is None, x["name"]))
    return out


@router.get("/all-agents")
async def all_agents(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Every agent across every environment's latest complete scan (default view)."""
    latest = await _latest_scan_per_env(session)
    env_rows = {
        e.id: e for e in (await session.execute(select(Environment))).scalars().all()
    }
    out: list[dict] = []
    for env_id, scan in latest.items():
        rows = (
            await session.execute(
                select(AgentScore).where(AgentScore.scan_id == scan.id)
            )
        ).scalars().all()
        env_name = env_rows[env_id].display_name if env_id in env_rows else f"Environment {env_id}"
        for a in rows:
            out.append({
                "bot_id": a.bot_id,
                "agent_name": a.agent_name,
                "solution_name": a.solution_name,
                "publish_state": a.publish_state,
                "score": a.score,
                "grade": a.grade,
                "scan_id": a.scan_id,
                "environment_id": a.environment_id,
                "environment_name": env_name,
            })
    return out


@router.get("/agents")
async def agents(scan_id: int, session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Every agent in a scan with its own score/grade (the agent list)."""
    rows = (
        await session.execute(
            select(AgentScore).where(AgentScore.scan_id == scan_id).order_by(AgentScore.score)
        )
    ).scalars().all()
    return [
        {
            "bot_id": a.bot_id,
            "agent_name": a.agent_name,
            "solution_name": a.solution_name,
            "publish_state": a.publish_state,
            "score": a.score,
            "grade": a.grade,
            "scan_id": a.scan_id,
            "environment_id": a.environment_id,
        }
        for a in rows
    ]


async def _resolve_agent_name(session: AsyncSession, scan_id: int, bot_id: str) -> str | None:
    return await session.scalar(
        select(AgentScore.agent_name).where(
            AgentScore.scan_id == scan_id, AgentScore.bot_id == bot_id
        )
    )


@router.get("/agents/{bot_id}")
async def agent_detail(
    bot_id: str, scan_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    """Full scorecard for one agent within a scan."""
    score_row = await session.scalar(
        select(AgentScore).where(AgentScore.scan_id == scan_id, AgentScore.bot_id == bot_id)
    )
    if score_row is None:
        raise HTTPException(status_code=404, detail="Agent not found in this scan")
    label = score_row.agent_name

    findings = (
        await session.execute(
            select(Finding).where(Finding.scan_id == scan_id, Finding.agent_name == label)
            .order_by(Finding.id)
        )
    ).scalars().all()
    judge = await session.scalar(
        select(JudgeResult).where(JudgeResult.scan_id == scan_id, JudgeResult.agent_name == label)
    )
    telem = await session.scalar(
        select(TelemetrySnapshot).where(
            TelemetrySnapshot.scan_id == scan_id, TelemetrySnapshot.agent_name == label
        )
    )

    # Agent metadata (created/modified/creator) + environment display name.
    agent_row = None
    if bot_id:
        agent_row = await session.scalar(select(Agent).where(Agent.bot_id == bot_id))
    env_name = None
    env_guid = None
    if score_row.environment_id is not None:
        env = await session.get(Environment, score_row.environment_id)
        env_name = env.display_name if env else None
        env_guid = env.environment_guid if env else None

    # Build maker-portal / Copilot Studio deep links when we have the ids.
    agent_url = None
    solution_url = None
    if env_guid and bot_id:
        agent_url = (
            f"https://copilotstudio.microsoft.com/environments/{env_guid}"
            f"/bots/{bot_id}/overview"
        )
    if env_guid and score_row.solution_id:
        solution_url = (
            f"https://make.powerapps.com/environments/{env_guid}"
            f"/solutions/{score_row.solution_id}"
        )

    return {
        "bot_id": bot_id,
        "agent_name": label,
        "solution_name": score_row.solution_name,
        "solution_id": score_row.solution_id,
        "solution_url": solution_url,
        "agent_url": agent_url,
        "publish_state": score_row.publish_state,
        "score": score_row.score,
        "grade": score_row.grade,
        "scan_id": scan_id,
        "environment_id": score_row.environment_id,
        "environment_name": env_name,
        "environment_guid": env_guid,
        "schema_name": agent_row.schema_name if agent_row else None,
        "model_hint": agent_row.model_hint if agent_row else None,
        "created_on": agent_row.created_on.isoformat() if (agent_row and agent_row.created_on) else None,
        "modified_on": agent_row.modified_on.isoformat() if (agent_row and agent_row.modified_on) else None,
        "created_by_name": agent_row.created_by_name if agent_row else None,
        "created_by_upn": agent_row.created_by_upn if agent_row else None,
        "findings": [
            {
                "rule_id": f.rule_id, "name": f.name, "severity": f.severity, "status": f.status,
                "manual_review": f.manual_review, "weight": f.weight, "scope": f.scope,
                "details": f.details, "pp_reference": f.pp_reference,
            }
            for f in findings
        ],
        "judge": None if judge is None else {
            "skipped": judge.skipped, "error": judge.error, "clarity": judge.clarity,
            "scope_discipline": judge.scope_discipline, "persona_defined": judge.persona_defined,
            "orchestrator_pattern_detected": judge.orchestrator_pattern_detected,
            "child_pattern_detected": judge.child_pattern_detected,
            "output_format_guidance": judge.output_format_guidance,
            "top_strengths": judge.top_strengths, "top_weaknesses": judge.top_weaknesses,
            "recommended_changes": judge.recommended_changes, "summary": judge.summary,
        },
        "telemetry": None if telem is None else {
            "window_days": telem.window_days, "run_count": telem.run_count,
            "error_count": telem.error_count, "p95_latency_ms": telem.p95_latency_ms,
            "source": telem.source,
        },
    }


@router.get("/agents/{bot_id}/history")
async def agent_history(
    bot_id: str, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """Daily score history for one agent (one point per scan it appeared in)."""
    rows = (
        await session.execute(
            select(AgentScore).where(AgentScore.bot_id == bot_id).order_by(AgentScore.captured_at)
        )
    ).scalars().all()
    return [
        {
            "scan_id": a.scan_id,
            "score": a.score,
            "grade": a.grade,
            "captured_at": a.captured_at.isoformat() if a.captured_at else None,
        }
        for a in rows
    ]


@router.get("/rule-history")
async def rule_history(
    bot_id: str, rule_id: str, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """History of a single rule's outcome for one agent, across scans."""
    # Map bot_id -> agent_name via any AgentScore row, then walk findings by scan.
    label = await session.scalar(
        select(AgentScore.agent_name).where(AgentScore.bot_id == bot_id).limit(1)
    )
    if not label:
        return []
    rows = (
        await session.execute(
            select(Finding, Scan.finished_at)
            .join(Scan, Scan.id == Finding.scan_id)
            .where(Finding.agent_name == label, Finding.rule_id == rule_id)
            .order_by(Scan.started_at)
        )
    ).all()
    return [
        {
            "scan_id": f.scan_id,
            "status": f.status,
            "details": f.details,
            "captured_at": ts.isoformat() if ts else None,
        }
        for f, ts in rows
    ]


@router.get("/scan-progress")
async def scan_progress(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Any scans currently running, with a live agents-done / total counter."""
    rows = (
        await session.execute(select(Scan).where(Scan.status == "running"))
    ).scalars().all()
    return [
        {
            "scan_id": s.id,
            "environment_id": s.environment_id,
            "source": s.source,
            "agents_done": s.agents_done,
            "agent_count": s.agent_count,
            "started_at": s.started_at.isoformat() if s.started_at else None,
        }
        for s in rows
    ]


@router.get("/scans")
async def list_scans(limit: int = 50, session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (
        await session.execute(
            select(Scan).order_by(Scan.started_at.desc()).limit(min(limit, 200))
        )
    ).scalars().all()
    env_rows = {e.id: e for e in (await session.execute(select(Environment))).scalars().all()}
    return [
        {
            "id": s.id,
            "environment": "Demo (bundled)" if s.environment_id is None else (
                env_rows[s.environment_id].display_name if s.environment_id in env_rows
                else f"Environment {s.environment_id}"
            ),
            "source": s.source,
            "trigger": s.trigger,
            "agent_count": s.agent_count,
            "avg_score": s.score,
            "grade": s.grade,
            "started_at": s.started_at.isoformat() if s.started_at else None,
        }
        for s in rows
    ]
