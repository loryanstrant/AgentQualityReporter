"""Entra ID single sign-on via Azure Container Apps 'Easy Auth'.

When deployed with the Microsoft identity provider enabled, Azure authenticates
the user in front of the container and injects the signed-in identity as request
headers the client cannot forge. We run Easy Auth in AllowAnonymous mode so it
only adds identity when present and never blocks the password gate.

This module reads that identity, optionally checks membership of a configured
Entra security group (app-only Graph ``checkMemberGroups`` using the stored SP
credentials), and lets the caller mint the app's JWT. SSO users are viewers;
administration stays behind the password gate.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import time
from dataclasses import dataclass, field

import httpx
import msal
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from shared.crypto import decrypt
from shared.models import AppConfig

logger = logging.getLogger("api.easyauth")

_OID_CLAIMS = (
    "http://schemas.microsoft.com/identity/claims/objectidentifier",
    "oid",
)
_NAME_CLAIMS = (
    "preferred_username",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn",
    "upn",
    "email",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    "name",
)
_GROUP_CLAIM = "groups"

_GROUP_TTL_SECONDS = 300
_group_cache: dict[tuple[str, str], tuple[float, bool]] = {}


@dataclass
class EasyAuthPrincipal:
    object_id: str
    name: str
    groups: list[str] = field(default_factory=list)


def _claims_map(principal_json: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in principal_json.get("claims", []) or []:
        typ, val = c.get("typ"), c.get("val")
        if typ and val is not None and typ not in out:
            out[typ] = val
    return out


def _all_claim_values(principal_json: dict, typ: str) -> list[str]:
    return [
        c.get("val")
        for c in (principal_json.get("claims", []) or [])
        if c.get("typ") == typ and c.get("val")
    ]


def parse_principal(request: Request) -> EasyAuthPrincipal | None:
    b64 = request.headers.get("x-ms-client-principal")
    principal_json: dict = {}
    if b64:
        try:
            principal_json = json.loads(base64.b64decode(b64).decode("utf-8"))
        except (binascii.Error, ValueError, UnicodeDecodeError):
            principal_json = {}

    claims = _claims_map(principal_json)
    oid = next((claims[c] for c in _OID_CLAIMS if c in claims), None) or request.headers.get(
        "x-ms-client-principal-id"
    )
    name = (
        next((claims[c] for c in _NAME_CLAIMS if c in claims), None)
        or request.headers.get("x-ms-client-principal-name")
    )
    if not oid or not name:
        return None
    groups = _all_claim_values(principal_json, _GROUP_CLAIM)
    return EasyAuthPrincipal(object_id=oid, name=name, groups=groups)


async def _graph_check_member_groups(
    cfg: AppConfig, user_id: str, group_ids: list[str]
) -> list[str]:
    app = msal.ConfidentialClientApplication(
        cfg.client_id,
        authority=f"https://login.microsoftonline.com/{cfg.tenant_id}",
        client_credential=decrypt(cfg.client_secret_encrypted),
    )
    import asyncio

    result = await asyncio.to_thread(
        app.acquire_token_for_client, scopes=["https://graph.microsoft.com/.default"]
    )
    token = result.get("access_token")
    if not token:
        raise RuntimeError(result.get("error_description") or "token failed")
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/checkMemberGroups"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"groupIds": group_ids},
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"checkMemberGroups {resp.status_code}: {resp.text[:200]}")
    return list(resp.json().get("value", []))


async def is_group_member(
    principal: EasyAuthPrincipal, group_id: str, session: AsyncSession
) -> bool:
    """True when the principal belongs to ``group_id``. Fails closed."""
    if not group_id:
        return True
    if group_id in principal.groups:
        return True

    key = (principal.object_id, group_id)
    hit = _group_cache.get(key)
    now = time.monotonic()
    if hit and (now - hit[0]) < _GROUP_TTL_SECONDS:
        return hit[1]

    cfg = await session.get(AppConfig, 1)
    if cfg is None or not (cfg.tenant_id and cfg.client_id and cfg.client_secret_encrypted):
        return False
    try:
        matched = await _graph_check_member_groups(cfg, principal.object_id, [group_id])
        allowed = group_id in matched
    except Exception as exc:  # network / Graph — fail closed
        logger.warning("Group membership check failed for %s: %s", principal.name, exc)
        allowed = False

    _group_cache[key] = (now, allowed)
    return allowed


def reset_group_cache() -> None:
    _group_cache.clear()
