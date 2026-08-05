"""Scan orchestrator: collect -> score each agent -> judge -> persist.

A scan reads one environment (the bundled ``demo`` set or a live ``dataverse``
environment) and scores **each agent independently**: every agent is evaluated
against the agent-level rules plus the solution-level rules of the solution it
belongs to, producing its own score/grade. Per-agent scores are stored so the
agent list and daily history can be rendered.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from statistics import mean

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from engine.demo import demo_environment
from engine.llm_judge import judge_agent, judge_available
from engine.loader import ENGINE_VERSION, catalogue_hash, load_model_config, load_rules
from engine.static_rules import apply_rule_configs, grade_for_score, run_static_rules
from shared.crypto import decrypt
from shared.rules_config import load_effective_configs
from shared.models import (
    Agent,
    AgentScore,
    AppConfig,
    Environment,
    Finding,
    JudgeResult,
    Scan,
    TelemetrySnapshot,
)

logger = logging.getLogger("worker.scan")


class ScanError(RuntimeError):
    """Raised when a scan cannot proceed (e.g. environment not configured)."""


async def _gather_agents(session, *, source: str, environment_id: int | None):
    """Return (agents, environment)."""
    if source == "demo":
        return demo_environment()["agents"], None

    if source == "dataverse":
        if environment_id is None:
            raise ScanError("A dataverse scan needs an environment_id.")
        env = await session.get(Environment, environment_id)
        if env is None or not env.dataverse_url:
            raise ScanError("Environment not found or missing a Dataverse URL.")
        cfg = await session.get(AppConfig, 1)
        if cfg is None or not (cfg.tenant_id and cfg.client_id and cfg.client_secret_encrypted):
            raise ScanError("Service-principal credentials are not configured.")
        from worker.dataverse import collect_environment

        data = await collect_environment(
            org_url=env.dataverse_url,
            tenant_id=cfg.tenant_id,
            client_id=cfg.client_id,
            client_secret=decrypt(cfg.client_secret_encrypted),
        )
        guid = data.get("environment_guid")
        if guid and env.environment_guid != guid:
            env.environment_guid = guid
            await session.commit()
        await _enrich_telemetry(env, data["agents"])
        return data["agents"], env

    raise ScanError(f"Unknown scan source: {source}")


async def _enrich_telemetry(env: Environment, agents: list[dict]) -> None:
    if not env.app_insights_app_id or not env.app_insights_key_encrypted:
        return
    from worker.appinsights import fetch_agent_telemetry

    api_key = decrypt(env.app_insights_key_encrypted)
    for agent in agents:
        telem = await fetch_agent_telemetry(
            app_id=env.app_insights_app_id, api_key=api_key,
            agent_name=agent.get("display_name") or "",
        )
        if telem:
            agent["telemetry"] = telem
            if telem.get("run_count"):
                agent["telemetry_app_insights_key"] = agent.get("telemetry_app_insights_key") or "observed"


async def run_scan(
    session_factory: async_sessionmaker,
    *,
    source: str = "demo",
    environment_id: int | None = None,
    trigger: str = "manual",
) -> dict:
    """Execute one environment scan, scoring each agent independently."""
    async with session_factory() as session:
        agents, env = await _gather_agents(session, source=source, environment_id=environment_id)
        cfg = await session.get(AppConfig, 1)
        rules = load_rules()
        model_config = load_model_config().get("model", {})
        rule_configs = await load_effective_configs(session)

        base_url = cfg.aoai_base_url if cfg else None
        model = cfg.aoai_model if cfg else None
        api_key = decrypt(cfg.aoai_key_encrypted) if (cfg and cfg.aoai_key_encrypted) else None
        judge_on = judge_available(base_url, model, api_key)

        scan = Scan(
            environment_id=environment_id,
            solution_name=None,
            source=source,
            trigger=trigger,
            status="running",
            agent_count=len(agents),
            agents_done=0,
            engine_version=ENGINE_VERSION,
            catalogue_hash=catalogue_hash(),
        )
        session.add(scan)
        await session.commit()  # make the running scan + its progress visible

        try:
            per_agent_scores: list[int] = []
            for idx, agent in enumerate(agents):
                label = agent.get("display_name") or agent.get("folder") or "unknown"
                parsed_single = {
                    "source": source,
                    "solution": agent.get("solution") or {},
                    "connection_references": agent.get("connection_references") or [],
                    "environment_variables": agent.get("environment_variables") or [],
                    "bots": [agent],
                }
                result = run_static_rules(
                    parsed_single, rules,
                    icon_config={"known_default_hashes": []},
                    model_config=model_config,
                )
                apply_rule_configs(result, rule_configs)
                per_agent_scores.append(result.score)

                for f in result.findings:
                    session.add(Finding(
                        scan_id=scan.id, rule_id=f.rule_id, name=f.name, severity=f.severity,
                        status=f.status, manual_review=f.manual_review, weight=f.weight,
                        scope=f.scope, agent_name=label, details=f.details, pp_reference=f.pp_reference,
                    ))

                verdict = judge_agent(agent, base_url=base_url, model=model, api_key=api_key) if judge_on else None
                _persist_judge(session, scan.id, label, verdict)

                telem = agent.get("telemetry") or {}
                if telem:
                    session.add(TelemetrySnapshot(
                        scan_id=scan.id, agent_name=label, window_days=telem.get("window_days", 30),
                        run_count=telem.get("run_count"), error_count=telem.get("error_count"),
                        p95_latency_ms=telem.get("p95_latency_ms"),
                        source="app_insights" if source == "dataverse" else "demo",
                    ))

                sol = agent.get("solution") or {}
                session.add(AgentScore(
                    scan_id=scan.id, environment_id=environment_id, bot_id=agent.get("bot_id"),
                    agent_name=label,
                    solution_name=sol.get("display_name") or sol.get("unique_name"),
                    solution_id=sol.get("solution_id"),
                    publish_state=agent.get("publish_state"), score=result.score, grade=result.grade,
                ))
                await _upsert_agent(session, environment_id, agent)

                # Persist progress so the UI can show a live counter.
                scan.agents_done = idx + 1
                await session.commit()

            rollup = round(mean(per_agent_scores)) if per_agent_scores else None
            scan.score = rollup
            scan.grade = grade_for_score(rollup) if rollup is not None else None
            scan.status = "complete"
            scan.finished_at = datetime.now(timezone.utc)
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            scan.status = "failed"
            scan.detail = str(exc)[:500]
            scan.finished_at = datetime.now(timezone.utc)
            await session.commit()
            logger.exception("Scan %s failed", scan.id)
            raise

        logger.info("Scan %s complete: rollup=%s agents=%s source=%s",
                    scan.id, scan.score, len(agents), source)
        return {"scan_id": scan.id, "score": scan.score, "grade": scan.grade,
                "agent_count": len(agents)}


def _persist_judge(session, scan_id: int, label: str, verdict: dict | None) -> None:
    if verdict is None:
        session.add(JudgeResult(scan_id=scan_id, agent_name=label, skipped=True,
                                summary="LLM judge not configured."))
        return
    if verdict.get("skipped"):
        session.add(JudgeResult(scan_id=scan_id, agent_name=label, skipped=True,
                                summary=verdict.get("reason")))
        return
    if verdict.get("error"):
        session.add(JudgeResult(scan_id=scan_id, agent_name=label, error=verdict["error"]))
        return
    session.add(JudgeResult(
        scan_id=scan_id, agent_name=label,
        clarity=verdict.get("clarity"), scope_discipline=verdict.get("scope_discipline"),
        persona_defined=verdict.get("persona_defined"),
        orchestrator_pattern_detected=verdict.get("orchestrator_pattern_detected"),
        child_pattern_detected=verdict.get("child_pattern_detected"),
        output_format_guidance=verdict.get("output_format_guidance"),
        top_strengths=verdict.get("top_strengths"), top_weaknesses=verdict.get("top_weaknesses"),
        recommended_changes=verdict.get("recommended_changes"), summary=verdict.get("summary"),
    ))


async def _upsert_agent(session, environment_id: int | None, agent: dict) -> None:
    bot_id = agent.get("bot_id")
    existing = None
    if bot_id:
        existing = await session.scalar(select(Agent).where(Agent.bot_id == bot_id))
    if existing is None:
        existing = Agent(environment_id=environment_id, bot_id=bot_id)
        session.add(existing)
    existing.environment_id = environment_id
    existing.display_name = agent.get("display_name")
    existing.schema_name = agent.get("schema_name")
    existing.description = agent.get("description")
    existing.model_hint = agent.get("model")
    existing.publish_state = agent.get("publish_state")
    existing.icon_hash = agent.get("icon_hash")
    existing.created_on = _parse_dt(agent.get("created_on"))
    existing.modified_on = _parse_dt(agent.get("modified_on"))
    existing.created_by_name = agent.get("created_by_name")
    existing.created_by_upn = agent.get("created_by_upn")


def _parse_dt(value):
    """Coerce a Dataverse ISO timestamp string to a datetime, or None."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
