"""Async Dataverse Web API client (app-only / client credentials).

This is the collector that replaces the static solution-ZIP parser. Reading agents
live from Dataverse carries fields the export drops — description, Application
Insights configuration, authentication mode, and publish state — which is what
turns AGT-002 / AGT-007 / AGT-010 / AGT-011 from 'manual review' into scored rules.

Field mappings follow the documented Copilot Studio Dataverse tables (``bot``,
``botcomponent``, ``connectionreference``, ``environmentvariabledefinition``,
``solution``). Some column names vary between Dataverse versions; every lookup is
defensive (missing -> None) and the exact live column names should be confirmed
against a real environment (see the transformation plan, Phase 2 risk #1).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from typing import Any

import httpx
import msal
import yaml

logger = logging.getLogger("worker.dataverse")

_API_VERSION = "v9.2"
_TIMEOUT = 60.0

# Copilot Studio out-of-the-box system topics (schemaname suffix after ".topic.").
# A bot that only ships these has no custom conversational design (AGT-005).
SYSTEM_TOPICS = frozenset({
    "ConversationStart", "EndofConversation", "Escalate", "Fallback", "Goodbye",
    "Greeting", "MultipleTopicsMatched", "OnError", "ResetConversation", "Search",
    "Signin", "StartOver", "ThankYou",
})

# System / default solutions an agent may also belong to. Being *only* in these
# means the agent isn't packaged in a real solution (SOL-001 fails). Detection is
# by unique name AND friendly name because the CDS default solution's unique name
# is environment-specific (e.g. "Crc9a99"). A real solution — managed OR unmanaged
# — is a valid owning solution.
_SYSTEM_SOLUTION_UNIQUE = frozenset({"default", "active", "system"})
_SYSTEM_SOLUTION_FRIENDLY = frozenset({
    "common data services default solution",
    "default solution",
    "system solution",
    "active solution",
})


def _is_system_solution(sol: dict) -> bool:
    uname = (sol.get("uniquename") or "").lower()
    fname = (sol.get("friendlyname") or "").lower()
    return uname in _SYSTEM_SOLUTION_UNIQUE or fname in _SYSTEM_SOLUTION_FRIENDLY


class DataverseError(RuntimeError):
    """Raised when Dataverse returns an unrecoverable error."""


class DataverseAuthError(DataverseError):
    """Raised when a client-credentials token cannot be acquired."""


class DataverseClient:
    """Thin async wrapper over the Dataverse Web API endpoints we need."""

    def __init__(
        self,
        *,
        org_url: str,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        concurrency: int = 8,
    ) -> None:
        self._org_url = org_url.rstrip("/")
        self._base = f"{self._org_url}/api/data/{_API_VERSION}"
        self._app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
        self._scope = [f"{self._org_url}/.default"]
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        self._sem = asyncio.Semaphore(concurrency)

    async def __aenter__(self) -> "DataverseClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def token(self) -> str:
        result = await asyncio.to_thread(
            self._app.acquire_token_for_client, scopes=self._scope
        )
        tok = result.get("access_token")
        if not tok:
            raise DataverseAuthError(
                result.get("error_description") or result.get("error") or "token failed"
            )
        return tok

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self.token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Prefer": 'odata.include-annotations="*"',
        }
        url = path if path.startswith("http") else f"{self._base}/{path}"
        async with self._sem:
            resp = await self._client.get(url, params=params, headers=headers)
        if resp.status_code >= 400:
            raise DataverseError(f"Dataverse {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    async def _list(self, entity: str, params: dict[str, Any] | None = None) -> list[dict]:
        rows: list[dict] = []
        data = await self._get(entity, params)
        rows.extend(data.get("value", []))
        while data.get("@odata.nextLink"):
            data = await self._get(data["@odata.nextLink"])
            rows.extend(data.get("value", []))
        return rows

    # -- high-level collectors ------------------------------------------
    async def whoami(self) -> dict[str, Any]:
        return await self._get("WhoAmI")

    async def list_bots(self) -> list[dict]:
        params = {
            "$select": (
                "botid,name,schemaname,authenticationmode,"
                "applicationmanifestinformation,configuration,statecode,statuscode,"
                "publishedon,createdon,modifiedon"
            ),
        }
        return await self._list("bots", params)

    async def list_botcomponents(self, bot_id: str) -> list[dict]:
        params = {
            "$select": "botcomponentid,name,schemaname,componenttype,content,data",
            "$filter": f"_parentbotid_value eq {bot_id}",
        }
        return await self._list("botcomponents", params)

    async def list_connection_references(self) -> list[dict]:
        params = {"$select": "connectionreferenceid,connectionreferencelogicalname,connectionreferencedisplayname"}
        return await self._list("connectionreferences", params)

    async def list_environment_variables(self) -> list[dict]:
        params = {"$select": "environmentvariabledefinitionid,schemaname,displayname,type"}
        return await self._list("environmentvariabledefinitions", params)

    async def get_solution(self, unique_name: str | None) -> dict | None:
        params = {
            "$select": "solutionid,uniquename,version,ismanaged",
            "$expand": "publisherid($select=customizationprefix,uniquename)",
        }
        if unique_name:
            params["$filter"] = f"uniquename eq '{unique_name}'"
        rows = await self._list("solutions", params)
        return rows[0] if rows else None


def _extract_instructions(components: list[dict]) -> str:
    """Pull instruction text out of the GPT/agent botcomponent, best-effort."""
    for c in components:
        content = c.get("content") or c.get("data")
        if not content:
            continue
        text = content if isinstance(content, str) else json.dumps(content)
        # Modern Copilot Studio stores instructions inside the GPT component YAML/JSON.
        for marker in ("instructions:", '"instructions"', "gptInstructions"):
            if marker in text:
                return text
    return ""


async def collect_dataverse(
    *,
    org_url: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    concurrency: int = 8,
) -> dict[str, Any]:
    """Read a live environment and return the ``parsed`` dict the engine expects."""
    async with DataverseClient(
        org_url=org_url,
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        concurrency=concurrency,
    ) as client:
        bots_raw = await client.list_bots()
        crefs = await client.list_connection_references()
        envvars = await client.list_environment_variables()
        solution = await client.get_solution(None)

        bots: list[dict[str, Any]] = []
        for b in bots_raw:
            bot_id = b.get("botid")
            components = await client.list_botcomponents(bot_id) if bot_id else []
            instr = _extract_instructions(components)
            auth_raw = b.get("authenticationmode")
            auth_map = {0: "none", 1: "integrated", 2: "manual"}
            bots.append(
                {
                    "folder": b.get("schemaname") or b.get("name"),
                    "bot_id": bot_id,
                    "schema_name": b.get("schemaname"),
                    "display_name": b.get("name"),
                    "description": b.get("description") or "",
                    "instructions": instr,
                    "raw_text_for_judge": instr,
                    "topics": [],
                    "user_topics": [c["name"] for c in components if c.get("componenttype") == 0],
                    "system_topics": [],
                    "modified_system_topics": [],
                    "suggested_prompts": [],
                    # App Insights connection is carried on the bot 'configuration'
                    # column (JSON) in live data — absent from the static export.
                    "telemetry_app_insights_key": _app_insights_key(b.get("configuration")),
                    "telemetry": {},
                    "model": "",
                    "icon_present": False,
                    "icon_hash": "",
                    "auth_mode": auth_map.get(auth_raw, str(auth_raw or "")),
                    "published": bool(b.get("publishedon")),
                    "publish_state": "published" if b.get("publishedon") else "unpublished",
                }
            )

        pub = (solution or {}).get("publisherid") or {}
        return {
            "source": "dataverse",
            "solution": {
                "found": solution is not None,
                "unique_name": (solution or {}).get("uniquename"),
                "version": (solution or {}).get("version"),
                "publisher_prefix": pub.get("customizationprefix"),
                "publisher_name": pub.get("uniquename"),
            },
            "connection_references": [
                {"logical_name": c.get("connectionreferencelogicalname")} for c in crefs
            ],
            "environment_variables": [
                {"schema_name": e.get("schemaname")} for e in envvars
            ],
            "bots": bots,
        }


def _app_insights_key(configuration: Any) -> str | None:
    if not configuration:
        return None
    try:
        cfg = configuration if isinstance(configuration, dict) else json.loads(configuration)
    except (ValueError, TypeError):
        return None
    for key in ("applicationInsightsConnectionString", "instrumentationKey", "appInsightsKey"):
        if cfg.get(key):
            return str(cfg[key])
    return None


def _parse_gpt_yaml(data: str) -> tuple[str, str, list[str]]:
    """Extract (instructions, model_hint, suggested_prompts) from the GPT
    component's ``data`` YAML. Falls back to regex when YAML parsing fails."""
    instructions, model, prompts = "", "", []
    if not data:
        return instructions, model, prompts
    doc: dict[str, Any] = {}
    try:
        loaded = yaml.safe_load(data)
        if isinstance(loaded, dict):
            doc = loaded
    except Exception:  # noqa: BLE001 - malformed YAML, fall back to regex
        doc = {}

    if doc:
        instructions = str(doc.get("instructions") or "").strip()
        ai = doc.get("aISettings") or doc.get("aiSettings") or {}
        model = str(((ai.get("model") or {}) if isinstance(ai, dict) else {}).get("modelNameHint") or "")
        for key in ("conversationStarters", "suggestedPrompts", "starterPrompts"):
            val = doc.get(key)
            if isinstance(val, list) and val:
                prompts = [
                    (p.get("text") if isinstance(p, dict) else str(p)) for p in val
                ]
                break

    if not model:
        m = re.search(r"modelNameHint:\s*([A-Za-z0-9_.\-]+)", data)
        if m:
            model = m.group(1)
    if not instructions:
        m = re.search(r"instructions:\s*\|-?\s*\n(.*?)(?:\n[A-Za-z]\w*:|\Z)", data, re.S)
        if m:
            instructions = m.group(1).strip()
    return instructions, model, [p for p in prompts if p]


async def _solution_object_ids(client: "DataverseClient", solution_id: str) -> set[str]:
    rows = await client._list(
        "solutioncomponents",
        {"$select": "objectid", "$filter": f"_solutionid_value eq {solution_id}", "$top": 5000},
    )
    return {r.get("objectid") for r in rows if r.get("objectid")}


async def _owning_solution(
    client: "DataverseClient", bot_id: str, sol_by_id: dict[str, dict]
) -> dict | None:
    """Return the agent's owning solution (custom, managed or unmanaged), or None
    when it lives only in the default/system solutions.

    A managed solution IS a real packaged solution (built elsewhere and imported),
    so it counts. Only the default/system solutions are excluded. When an agent is
    in several real solutions, an unmanaged (dev) one is preferred over a managed
    (imported) one, but either is valid.
    """
    rows = await client._list(
        "solutioncomponents",
        {"$select": "_solutionid_value", "$filter": f"objectid eq {bot_id}", "$top": 50},
    )
    candidates: list[dict] = []
    for r in rows:
        sol = sol_by_id.get(r.get("_solutionid_value"))
        if not sol or _is_system_solution(sol):
            continue
        candidates.append(sol)
    if not candidates:
        return None
    # Prefer unmanaged (dev) over managed (imported); both are valid.
    candidates.sort(key=lambda s: bool(s.get("ismanaged")))
    return candidates[0]


def _human_creator(bot: dict) -> tuple[str | None, str | None]:
    """Return (display_name, upn) of the human who created the agent.

    When an app/service principal creates the bot 'on behalf of' a maker, the
    human is in ``createdonbehalfby``; otherwise ``createdby``. App/system users
    carry a non-null ``applicationid`` — we skip those in favour of the human.
    """
    onbehalf = bot.get("createdonbehalfby") or {}
    createdby = bot.get("createdby") or {}

    def is_human(u: dict) -> bool:
        return bool(u) and not u.get("applicationid") and bool(u.get("fullname"))

    for cand in (onbehalf, createdby):
        if is_human(cand):
            upn = cand.get("domainname") or cand.get("internalemailaddress")
            return cand.get("fullname"), upn
    # Fall back to any name we have, even if it's an app user.
    for cand in (onbehalf, createdby):
        if cand.get("fullname"):
            return cand.get("fullname"), cand.get("domainname") or cand.get("internalemailaddress")
    return None, None


async def collect_environment(
    *,
    org_url: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    concurrency: int = 8,
) -> dict[str, Any]:
    """Read a live environment and return a per-agent list, each carrying the
    agent-level fields AND its owning-solution context for solution-level rules."""
    async with DataverseClient(
        org_url=org_url, tenant_id=tenant_id, client_id=client_id,
        client_secret=client_secret, concurrency=concurrency,
    ) as client:
        bots = await client._list("bots", {
            "$select": (
                "botid,name,schemaname,authenticationmode,publishedon,statecode,"
                "statuscode,componentstate,configuration,iconbase64,createdon,modifiedon"
            ),
            "$expand": (
                "createdby($select=fullname,domainname,internalemailaddress,applicationid),"
                "createdonbehalfby($select=fullname,domainname,internalemailaddress,applicationid)"
            ),
            "$top": 500,
        })

        # --- default-icon detection: the default is the icon hash shared by
        # more than one agent (uncustomised agents share the stock icon). ---
        hash_counts: dict[str, int] = {}
        for b in bots:
            ib = b.get("iconbase64") or ""
            h = hashlib.sha256(ib.encode("utf-8")).hexdigest() if ib else ""
            b["_icon_hash"] = h
            if h:
                hash_counts[h] = hash_counts.get(h, 0) + 1
        default_hash = ""
        if hash_counts:
            cand = max(hash_counts, key=lambda k: hash_counts[k])
            if hash_counts[cand] > 1:
                default_hash = cand

        # --- solutions + connection-ref / env-var id sets (for membership) ---
        sols = await client._list("solutions", {
            "$select": "solutionid,uniquename,friendlyname,ismanaged,version",
            "$expand": "publisherid($select=customizationprefix,uniquename)",
            "$top": 500,
        })
        sol_by_id = {s["solutionid"]: s for s in sols}
        crefs = await client._list("connectionreferences", {
            "$select": "connectionreferenceid,connectionreferencelogicalname"})
        envvars = await client._list("environmentvariabledefinitions", {
            "$select": "environmentvariabledefinitionid,schemaname"})
        cref_by_id = {c["connectionreferenceid"]: c for c in crefs}
        env_by_id = {e["environmentvariabledefinitionid"]: e for e in envvars}
        sol_objids_cache: dict[str, set[str]] = {}

        agents: list[dict[str, Any]] = []
        for b in bots:
            bid = b["botid"]
            comps = await client._list("botcomponents", {
                "$select": "botcomponentid,name,schemaname,componenttype",
                "$filter": f"_parentbotid_value eq {bid}", "$top": 500})

            user_topics, system_topics = [], []
            for c in comps:
                if c.get("componenttype") == 9:
                    nm = str(c.get("schemaname", "")).split(".topic.")[-1]
                    label = c.get("name") or nm
                    (system_topics if nm in SYSTEM_TOPICS else user_topics).append(label)

            gpt = next((c for c in comps if c.get("componenttype") == 15
                        or str(c.get("schemaname", "")).endswith(".gpt.default")), None)
            description, instructions, model, prompts = "", "", "", []
            if gpt:
                full = await client._get(
                    f"botcomponents({gpt['botcomponentid']})", {"$select": "description,data"})
                description = (full.get("description") or "").strip()
                instructions, model, prompts = _parse_gpt_yaml(full.get("data") or "")

            owning = await _owning_solution(client, bid, sol_by_id)
            sol_crefs: list[dict] = []
            sol_envs: list[dict] = []
            if owning:
                sid = owning["solutionid"]
                if sid not in sol_objids_cache:
                    sol_objids_cache[sid] = await _solution_object_ids(client, sid)
                objids = sol_objids_cache[sid]
                sol_crefs = [{"logical_name": cref_by_id[i].get("connectionreferencelogicalname")}
                             for i in objids if i in cref_by_id]
                sol_envs = [{"schema_name": env_by_id[i].get("schemaname")}
                            for i in objids if i in env_by_id]

            pub = (owning or {}).get("publisherid") or {}
            published = bool(b.get("publishedon"))
            icon_hash = b.get("_icon_hash") or ""
            creator_name, creator_upn = _human_creator(b)
            agents.append({
                "source": "dataverse",
                "bot_id": bid,
                "folder": b.get("schemaname") or b.get("name"),
                "schema_name": b.get("schemaname"),
                "display_name": b.get("name"),
                "description": description,
                "instructions": instructions,
                "raw_text_for_judge": instructions,
                "model": model,
                "created_on": b.get("createdon"),
                "modified_on": b.get("modifiedon"),
                "created_by_name": creator_name,
                "created_by_upn": creator_upn,
                "topics": [*user_topics, *system_topics],
                "user_topics": user_topics,
                "system_topics": system_topics,
                "modified_system_topics": [],
                "suggested_prompts": prompts,
                "telemetry_app_insights_key": _app_insights_key(b.get("configuration")),
                "telemetry": {},
                "icon_present": bool(icon_hash),
                "icon_hash": icon_hash,
                "icon_is_custom": bool(icon_hash) and icon_hash != default_hash,
                "publish_state": "published" if published else "unpublished",
                "published": published,
                "solution": {
                    "found": owning is not None,
                    "solution_id": (owning or {}).get("solutionid"),
                    "unique_name": (owning or {}).get("uniquename"),
                    "display_name": (owning or {}).get("friendlyname"),
                    "version": (owning or {}).get("version"),
                    "is_managed": bool((owning or {}).get("ismanaged")),
                    "publisher_prefix": pub.get("customizationprefix"),
                    "publisher_name": pub.get("uniquename"),
                    "is_default": owning is None,
                },
                "connection_references": sol_crefs,
                "environment_variables": sol_envs,
            })

        environment_guid = await _resolve_environment_guid(client)
        return {
            "agents": agents,
            "default_icon_hash": default_hash,
            "environment_guid": environment_guid,
        }


async def _resolve_environment_guid(client: "DataverseClient") -> str | None:
    """Resolve the Power Platform environment GUID from the Dataverse org.

    RetrieveCurrentOrganization returns the org detail including EnvironmentId,
    which is the GUID used in Copilot Studio / maker-portal deep links.
    """
    try:
        data = await client._get("RetrieveCurrentOrganization(AccessType='Default')")
        return ((data.get("Detail") or {}).get("EnvironmentId")) or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not resolve environment GUID: %s", exc)
        return None


async def test_dataverse_connection(
    *, org_url: str, tenant_id: str, client_id: str, client_secret: str
) -> dict[str, Any]:
    """Lightweight connectivity check used by the admin 'Test connection' button."""
    try:
        async with DataverseClient(
            org_url=org_url,
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        ) as client:
            await client.token()
            who = await client.whoami()
            bots = await client.list_bots()
        return {
            "ok": True,
            "token_acquired": True,
            "org_reachable": True,
            "user_id": who.get("UserId"),
            "bots_found": len(bots),
            "detail": f"Connected. {len(bots)} agent(s) visible.",
        }
    except DataverseAuthError as exc:
        return {"ok": False, "token_acquired": False, "detail": f"Auth failed: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc)}

