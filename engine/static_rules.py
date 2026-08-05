"""Static rule implementations. Each rule returns a Finding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEVERITY_WEIGHTS = {
    "blocker": 10,
    "major": 5,
    "minor": 2,
    "info": 0,
}


@dataclass
class Finding:
    rule_id: str
    name: str
    severity: str
    status: str  # pass | fail | skipped
    details: str = ""
    pp_reference: str = ""
    scope: str = "solution"  # solution | bot:<name>
    manual_review: bool = False  # P&P item that can't be auto-scored from the solution export
    weight_override: int | None = None  # set from editable RuleConfig at scan time

    @property
    def weight(self) -> int:
        if self.manual_review or self.status != "fail":
            return 0
        if self.weight_override is not None:
            return max(0, self.weight_override)
        return SEVERITY_WEIGHTS.get(self.severity, 0)


def apply_rule_configs(result: "ScanResult", configs: dict[str, dict]) -> "ScanResult":
    """Drop findings for disabled rules and apply configured weight overrides.

    ``configs`` maps rule_id -> {"enabled": bool, "weight": int}. Rules not present
    in the map keep their catalogue-default behaviour.
    """
    kept: list[Finding] = []
    for f in result.findings:
        c = configs.get(f.rule_id)
        if c is not None:
            if not c.get("enabled", True):
                continue
            if c.get("weight") is not None:
                f.weight_override = c["weight"]
        kept.append(f)
    result.findings = kept
    return result


def grade_for_score(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    bots: list[dict[str, Any]] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    @property
    def score(self) -> int:
        deductions = sum(f.weight for f in self.findings)
        return max(0, min(100, 100 - deductions))

    @property
    def grade(self) -> str:
        return grade_for_score(self.score)


def run_static_rules(
    parsed: dict[str, Any],
    rules_config: list[dict[str, Any]],
    *,
    icon_config: dict[str, Any] | None = None,
    model_config: dict[str, Any] | None = None,
) -> ScanResult:
    result = ScanResult(bots=parsed.get("bots", []))
    rule_map = {r["id"]: r for r in rules_config}
    # Data-source fidelity. Live sources (Dataverse Web API / BAP / App Insights)
    # carry fields the static solution-ZIP export drops — description, telemetry
    # config, publish/auth state — so rules that were "manual review" when reading
    # a ZIP become fully scored pass/fail when the data is live.
    live = (parsed.get("source") or "zip") in {"dataverse", "demo"}
    default_icon_hashes = {
        h.lower() for h in (icon_config or {}).get("known_default_hashes", []) if h
    }
    # Build a case-insensitive lookup over modelNameHint → metadata.
    model_catalogue: dict[str, dict[str, Any]] = {}
    for key, meta in ((model_config or {}).get("catalogue") or {}).items():
        if isinstance(meta, dict):
            model_catalogue[key.lower()] = {
                "hint": key,
                "display": meta.get("display") or key,
                "status": (meta.get("status") or "unknown").lower(),
                "category": meta.get("category") or "",
            }

    def rule(rule_id: str) -> tuple[str, str, str]:
        r = rule_map.get(rule_id, {})
        return r.get("name", rule_id), r.get("severity", "minor"), r.get("pp_reference", "")

    # ---- Solution-level rules (evaluated against the agent's owning solution) ----
    sol = parsed.get("solution") or {}
    is_default_only = bool(sol.get("is_default")) or not sol.get("found", True)
    name, sev, ref = rule("SOL-001")
    prefix = (sol.get("publisher_prefix") or "").lower()
    if is_default_only:
        result.add(Finding("SOL-001", name, sev, "fail",
                           "Agent is not packaged in a custom solution (only the default "
                           "solution). Add it to a proper custom solution with a custom publisher.", ref))
    elif not prefix:
        result.add(Finding("SOL-001", name, sev, "skipped",
                           "Publisher prefix not detected.", ref))
    elif prefix in {"new", "cr"}:
        result.add(Finding("SOL-001", name, sev, "fail",
                           f"Publisher prefix is '{prefix}'. Use a custom publisher prefix.", ref))
    else:
        result.add(Finding("SOL-001", name, sev, "pass",
                           f"Publisher prefix: '{prefix}'.", ref))

    name, sev, ref = rule("SOL-002")
    version = sol.get("version") or ""
    if is_default_only:
        result.add(Finding("SOL-002", name, sev, "skipped",
                           "No custom solution — versioning not applicable (see SOL-001).", ref))
    elif not version:
        result.add(Finding("SOL-002", name, sev, "skipped", "Version not detected.", ref))
    elif version.startswith("1.0.0.0"):
        result.add(Finding("SOL-002", name, sev, "fail",
                           f"Solution still at default version {version}. Increment as builds progress.", ref))
    else:
        result.add(Finding("SOL-002", name, sev, "pass", f"Version: {version}.", ref))

    # ---- Connection references ----
    name, sev, ref = rule("CON-001")
    crefs = parsed.get("connection_references") or []
    if crefs:
        names = sorted({(c.get("logical_name") or "?") for c in crefs})
        preview = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        result.add(Finding("CON-001", name, sev, "pass",
                           f"{len(crefs)} connection reference(s) defined: {preview}.", ref))
    else:
        result.add(Finding("CON-001", name, sev, "fail",
                           "No connection references found. Use connection references instead of hardcoded connections.", ref))

    # ---- Environment variables ----
    name, sev, ref = rule("ENV-001")
    envs = parsed.get("environment_variables") or []
    if envs:
        result.add(Finding("ENV-001", name, sev, "pass",
                           f"{len(envs)} environment variable definition(s) found.", ref))
    else:
        result.add(Finding("ENV-001", name, sev, "fail",
                           "No environment variable definitions found. Parameterise env-specific values.", ref))

    # ---- Per-bot rules ----
    bots = parsed.get("bots") or []
    if not bots:
        result.add(Finding("AGT-000", "Bots present in solution", "major", "fail",
                           "No bot/agent folders detected under bots/. Either the solution has no agent or the unpacked layout is non-standard.",
                           "Slide 11 - Agents"))
        return result

    for bot in bots:
        scope = f"bot:{bot.get('display_name') or bot.get('folder')}"

        name, sev, ref = rule("AGT-001")
        dn = (bot.get("display_name") or "").strip()
        if dn:
            result.add(Finding("AGT-001", name, sev, "pass", f"Display name: '{dn}'.", ref, scope))
        else:
            result.add(Finding("AGT-001", name, sev, "fail",
                               "Agent has no display name.", ref, scope))

        name, sev, ref = rule("AGT-002")
        desc = (bot.get("description") or "").strip()
        if len(desc) >= 50:
            result.add(Finding("AGT-002", name, sev, "pass",
                               f"Description present ({len(desc)} chars).", ref, scope))
        elif desc:
            result.add(Finding("AGT-002", name, sev, "fail",
                               f"Description too short ({len(desc)} chars). Expand to at least 50.",
                               ref, scope))
        elif live:
            # Live Dataverse read carries the description authoritatively, so a
            # missing/blank value is a genuine scored failure — no longer manual.
            result.add(Finding("AGT-002", name, sev, "fail",
                               "No description set on the agent (read live from Dataverse). "
                               "Add a meaningful description of at least 50 characters.",
                               ref, scope))
        else:
            # Reading a static solution export: modern Copilot Studio doesn't ship
            # the description field, so a missing value isn't a static-rule failure —
            # flag for manual review in Studio (the LLM judge also covers this).
            result.add(Finding("AGT-002", name, sev, "skipped",
                               "Description field is not present in the solution export. "
                               "Review the description inside Copilot Studio (the LLM judge also covers this).",
                               ref, scope, manual_review=True))

        name, sev, ref = rule("AGT-003")
        instr = (bot.get("instructions") or "").strip()
        agt003_passed = len(instr) >= 200
        if agt003_passed:
            result.add(Finding("AGT-003", name, sev, "pass",
                               f"Instructions present ({len(instr)} chars).", ref, scope))
        elif instr:
            result.add(Finding("AGT-003", name, sev, "fail",
                               f"Instructions too short ({len(instr)} chars). Expand to at least 200.",
                               ref, scope))
        else:
            result.add(Finding("AGT-003", name, sev, "fail",
                               "No instructions detected for this agent.", ref, scope))

        # AGT-004 is the upper-bound counterpart to AGT-003. If AGT-003 already
        # failed (instructions missing or too short) the upper-bound check is
        # meaningless noise — skip it instead of emitting a misleading "pass".
        name, sev, ref = rule("AGT-004")
        if not agt003_passed:
            reason = ("no instructions defined" if not instr
                      else f"instructions too short ({len(instr)} chars)")
            result.add(Finding("AGT-004", name, sev, "skipped",
                               f"Skipped — {reason} (see AGT-003).", ref, scope))
        elif len(instr) > 8000:
            result.add(Finding("AGT-004", name, sev, "fail",
                               f"Instructions exceed 8000 chars ({len(instr)}). Consider refactoring.",
                               ref, scope))
        else:
            result.add(Finding("AGT-004", name, sev, "pass",
                               f"Instructions within length budget ({len(instr)} chars).", ref, scope))

        name, sev, ref = rule("AGT-005")
        topics = bot.get("topics") or []
        system_topics = bot.get("system_topics") or []
        user_topics = bot.get("user_topics") or []
        modified_system = bot.get("modified_system_topics") or []
        if user_topics:
            sys_note = f" ({len(system_topics)} system topic(s) also present)" if system_topics else ""
            result.add(Finding("AGT-005", name, sev, "pass",
                               f"{len(user_topics)} user-created topic(s) defined{sys_note}.",
                               ref, scope))
        elif modified_system:
            # No new user topics, but at least one system topic carries
            # custom maker logic (env vars, flow calls, generative answers, etc.)
            # P&P guidance accepts this as a customised conversational design.
            mod_names = sorted({m["name"] for m in modified_system})
            preview_parts = []
            for m in modified_system[:3]:
                preview_parts.append(f"{m['name']} ({'; '.join(m['signals'][:2])})")
            preview = "; ".join(preview_parts)
            if len(modified_system) > 3:
                preview += f"; +{len(modified_system) - 3} more"
            result.add(Finding("AGT-005", name, sev, "pass",
                               f"{len(mod_names)} system topic(s) customised by the maker: {preview}.",
                               ref, scope))
        elif system_topics:
            # The bot only ships the out-of-the-box system topics with no
            # detected customisation — no conversational design has been added.
            result.add(Finding("AGT-005", name, sev, "fail",
                               f"Only unmodified system topics detected ({len(system_topics)}): "
                               f"{', '.join(sorted(system_topics))}. "
                               "Add a user-created topic, or customise a system topic.",
                               ref, scope))
        elif topics:
            # Legacy/unknown-shape fallback: topics found but we couldn't classify them.
            result.add(Finding("AGT-005", name, sev, "pass",
                               f"{len(topics)} topic(s) defined.", ref, scope))
        else:
            result.add(Finding("AGT-005", name, sev, "fail",
                               "No topics detected.", ref, scope))

        name, sev, ref = rule("AGT-006")
        prompts = bot.get("suggested_prompts") or []
        if len(prompts) >= 3:
            result.add(Finding("AGT-006", name, sev, "pass",
                               f"{len(prompts)} suggested prompt(s) configured.", ref, scope))
        elif prompts:
            result.add(Finding("AGT-006", name, sev, "fail",
                               f"Only {len(prompts)} suggested prompt(s). Aim for 3+.", ref, scope))
        else:
            result.add(Finding("AGT-006", name, sev, "fail",
                               "No suggested prompts configured.", ref, scope))

        name, sev, ref = rule("AGT-007")
        telem = bot.get("telemetry") or {}
        if telem.get("run_count") is not None:
            # Telemetry positively observed via the Application Insights query API
            # (the environment has App Insights wired up in Admin) — this is proof
            # the agent is emitting telemetry.
            result.add(Finding("AGT-007", name, sev, "pass",
                               f"Application Insights telemetry flowing: {telem.get('run_count')} run(s), "
                               f"{telem.get('error_count', 0)} error(s) in the last "
                               f"{telem.get('window_days', 30)} days.", ref, scope))
        elif bot.get("telemetry_app_insights_key"):
            result.add(Finding("AGT-007", name, sev, "pass",
                               "Application Insights connection configured.", ref, scope))
        else:
            # Copilot Studio stores the Application Insights connection OUTSIDE the
            # Dataverse tables (it's set in Studio → Settings → Advanced, and isn't
            # exposed on the bot/botcomponent rows), so its presence CANNOT be read
            # via the Dataverse Web API. We therefore never fail on absence — we flag
            # it for manual review unless telemetry is observed via the App Insights
            # query API (connect the environment's App Insights in Admin to auto-verify).
            result.add(Finding("AGT-007", name, sev, "skipped",
                               "Application Insights configuration isn't exposed via the Dataverse "
                               "API. Verify it in Copilot Studio, or connect this environment's "
                               "Application Insights in Admin so telemetry can be confirmed automatically.",
                               ref, scope, manual_review=True))

        name, sev, ref = rule("AGT-008")
        model = (bot.get("model") or "").strip()
        if not model:
            # The aiSettings block is only emitted when the maker explicitly
            # picks a non-default model. Its absence means the agent is on
            # the tenant-default model — informational, not a failure.
            result.add(Finding("AGT-008", name, sev, "pass",
                               "No aiSettings block found — agent is using the tenant-default "
                               "model (currently GPT-4.1 in most regions; see Microsoft Learn).",
                               ref, scope))
        else:
            meta = model_catalogue.get(model.lower())
            if not meta:
                # AGT-008 is `info` severity so this fail doesn't dock the score —
                # it just surfaces the unknown hint so the catalogue can be updated.
                result.add(Finding("AGT-008", name, sev, "fail",
                                   f"Model hint '{model}' is not in the model catalogue. "
                                   "Add it to model.catalogue in config.yml so future scans "
                                   "can classify it.",
                                   ref, scope))
            else:
                display = meta["display"]
                status = meta["status"]
                category = meta["category"]
                cat_note = f", {category} category" if category else ""
                if status == "retired":
                    result.add(Finding("AGT-008", name, sev, "fail",
                                       f"Model: {display}{cat_note}. This model is RETIRED — "
                                       "it will stop working within one month of retirement. "
                                       "Switch to a generally-available or default model.",
                                       ref, scope))
                elif status == "experimental":
                    result.add(Finding("AGT-008", name, sev, "fail",
                                       f"Model: {display}{cat_note}. This is an EXPERIMENTAL "
                                       "model — not recommended for production use (variable "
                                       "performance, may be unavailable, subject to preview terms).",
                                       ref, scope))
                elif status == "preview":
                    result.add(Finding("AGT-008", name, sev, "fail",
                                       f"Model: {display}{cat_note}. This is a PREVIEW model — "
                                       "not yet generally available. Validate behaviour before "
                                       "promoting the agent to production.",
                                       ref, scope))
                elif status == "default":
                    result.add(Finding("AGT-008", name, sev, "pass",
                                       f"Model: {display}{cat_note}. This is the current Copilot "
                                       "Studio default model.",
                                       ref, scope))
                elif status == "ga":
                    result.add(Finding("AGT-008", name, sev, "pass",
                                       f"Model: {display}{cat_note}. Generally available — "
                                       "production-ready.",
                                       ref, scope))
                else:
                    result.add(Finding("AGT-008", name, sev, "pass",
                                       f"Model: {display}{cat_note} (status: {status}).",
                                       ref, scope))

        # AGT-009 — agent icon. Every Copilot Studio agent ships an iconbase64,
        # so "has an icon" is meaningless. Instead we detect whether the agent has
        # a *custom* icon: the collector fingerprints every agent's icon and marks
        # the one shared across multiple agents as the tenant default. An agent
        # whose icon differs from that default has a custom (branded) icon.
        name, sev, ref = rule("AGT-009")
        icon_hash = (bot.get("icon_hash") or "").lower()
        hash_preview = icon_hash[:12] if icon_hash else ""
        if not bot.get("icon_present"):
            result.add(Finding("AGT-009", name, sev, "fail",
                               "No agent icon detected.", ref, scope))
        elif live:
            if bot.get("icon_is_custom"):
                result.add(Finding("AGT-009", name, sev, "pass",
                                   f"Custom icon detected (SHA-256 {hash_preview}…).",
                                   ref, scope))
            else:
                result.add(Finding("AGT-009", name, sev, "fail",
                                   "No custom icon — the agent uses the default Copilot "
                                   "Studio icon (shared with other agents). Upload a branded, "
                                   "on-theme icon.", ref, scope))
        elif icon_hash and icon_hash in default_icon_hashes:
            result.add(Finding("AGT-009", name, sev, "fail",
                               f"Icon matches a known Copilot Studio default "
                               f"(SHA-256 {hash_preview}…). Upload a branded icon.",
                               ref, scope))
        elif icon_hash and default_icon_hashes:
            result.add(Finding("AGT-009", name, sev, "pass",
                               f"Custom icon detected (SHA-256 {hash_preview}…).", ref, scope))
        else:
            result.add(Finding("AGT-009", name, sev, "skipped",
                               f"Icon present (SHA-256 {hash_preview}…). Verify in Copilot "
                               "Studio that it is branded.", ref, scope, manual_review=True))

    return result
