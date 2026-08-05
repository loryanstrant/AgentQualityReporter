"""Editable rule configuration: sync from the markdown catalogue into the DB and
load the effective config for scanning.

The markdown catalogue (engine/rules/rule-catalogue.md) remains the source of the
rule *set* (which rules exist, their severity and P&P reference). The DB overlay
(``rule_configs``) makes each rule's enabled flag, scoring weight, and explanation
editable from the admin UI. ``sync_rule_configs`` inserts any catalogue rules that
don't yet have a DB row (seeding defaults); it never overwrites admin edits.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.loader import DEFAULT_EXPLANATIONS, RULE_SCOPE, default_weight, load_rules
from shared.models import RuleConfig


async def sync_rule_configs(session: AsyncSession) -> None:
    """Ensure every catalogue rule has a RuleConfig row, and refresh the
    catalogue-owned metadata (name, severity, P&P reference, scope) on existing
    rows. User-owned fields (enabled, weight, explanation) are never overwritten.
    """
    existing = {
        r.rule_id: r for r in (await session.execute(select(RuleConfig))).scalars().all()
    }
    changed = False
    for rule in load_rules():
        rid = rule["id"]
        row = existing.get(rid)
        if row is None:
            session.add(
                RuleConfig(
                    rule_id=rid,
                    name=rule["name"],
                    severity=rule["severity"],
                    pp_reference=rule.get("pp_reference"),
                    scope=RULE_SCOPE.get(rid, "agent"),
                    enabled=True,
                    weight=default_weight(rule["severity"]),
                    explanation=DEFAULT_EXPLANATIONS.get(rid, ""),
                )
            )
            changed = True
        else:
            # Refresh catalogue-owned metadata (safe: not user-editable).
            if (row.name, row.severity, row.pp_reference, row.scope) != (
                rule["name"], rule["severity"], rule.get("pp_reference"),
                RULE_SCOPE.get(rid, "agent"),
            ):
                row.name = rule["name"]
                row.severity = rule["severity"]
                row.pp_reference = rule.get("pp_reference")
                row.scope = RULE_SCOPE.get(rid, "agent")
                changed = True
    if changed:
        await session.commit()


async def load_effective_configs(session: AsyncSession) -> dict[str, dict]:
    """Return rule_id -> {enabled, weight} for the scan engine."""
    await sync_rule_configs(session)
    rows = (await session.execute(select(RuleConfig))).scalars().all()
    return {r.rule_id: {"enabled": r.enabled, "weight": r.weight} for r in rows}
