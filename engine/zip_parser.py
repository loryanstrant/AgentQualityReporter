"""Parses an unpacked Power Platform solution and extracts data needed for quality checks.

The unpacked solution layout varies between Dataverse versions and component types.
This parser walks the tree, looks for known shapes (solution.xml, connection refs,
env vars, bot YAML/XML), and returns a dict of structured findings. Anything it
cannot locate is reported as None / empty so the rule engine can mark it 'not detected'.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

# Topic names that Copilot Studio ships out-of-the-box for every new agent.
# A solution that only contains these topics has effectively zero custom
# conversational design — AGT-005 should not pass on system topics alone.
# Regex signals that strongly indicate a system topic has been customised.
# Default system topics never reference custom env vars, flows, connectors,
# Power Fx Global variables, generative answers, or BeginDialog into a
# non-system topic — so any match is treated as user-applied modification.
_TOPIC_MOD_SIGNALS: tuple[tuple[str, str], ...] = (
    (r"\bEnv\.\w+", "references environment variable"),
    (r"\bGlobal\.\w+", "sets/reads custom Global variable"),
    (r"\bkind:\s*InvokeFlowAction\b", "invokes a Power Automate flow"),
    (r"\bkind:\s*InvokeConnectorAction\b", "invokes a connector action"),
    (r"\bkind:\s*InvokeSkillAction\b", "invokes a skill"),
    (r"\bkind:\s*SearchAndSummarizeContent\b", "uses generative answers / knowledge"),
    (r"\bkind:\s*HttpRequestAction\b", "makes a custom HTTP request"),
    (r"\bkind:\s*AdaptiveCardPrompt\b", "uses a custom adaptive card prompt"),
)

SYSTEM_TOPIC_NAMES = frozenset({
    "ConversationStart",
    "EndofConversation",
    "Escalate",
    "Fallback",
    "Goodbye",
    "Greeting",
    "MultipleTopicsMatched",
    "OnError",
    "ResetConversation",
    "Search",
    "Signin",
    "StartOver",
    "ThankYou",
})


def parse_solution(solution_root: Path) -> dict[str, Any]:
    """Walk a Power Platform unpacked-solution folder and extract structured metadata."""
    solution_root = Path(solution_root)

    customizations = _parse_customizations(solution_root)

    result: dict[str, Any] = {
        "solution_root": str(solution_root),
        "solution": _parse_solution_xml(solution_root),
        "connection_references": _parse_connection_references(solution_root, customizations),
        "environment_variables": _parse_environment_variables(solution_root),
        "bots": _parse_bots(solution_root),
        "customizations": customizations,
    }
    return result


def _parse_solution_xml(root: Path) -> dict[str, Any]:
    """Read solution.xml from the Other/ folder if present."""
    candidates = list(root.glob("**/solution.xml"))
    if not candidates:
        return {"found": False}

    try:
        tree = ET.parse(candidates[0])
        xml_root = tree.getroot()

        version = _xml_text(xml_root, ".//Version")
        unique_name = _xml_text(xml_root, ".//UniqueName")
        publisher_prefix = _xml_text(xml_root, ".//Publisher/CustomizationPrefix")
        publisher_name = _xml_text(xml_root, ".//Publisher/UniqueName")
        managed = _xml_text(xml_root, ".//Managed")

        return {
            "found": True,
            "path": str(candidates[0]),
            "version": version,
            "unique_name": unique_name,
            "publisher_prefix": publisher_prefix,
            "publisher_name": publisher_name,
            "managed": managed,
        }
    except Exception as exc:  # noqa: BLE001
        return {"found": True, "path": str(candidates[0]), "parse_error": str(exc)}


def _parse_customizations(root: Path) -> dict[str, Any]:
    """Pull connection references and workflow metadata out of customizations.xml.

    Modern Copilot Studio exports don't always create a top-level
    connectionreferences/ folder — instead, refs live inside <connectionreferences>
    in customizations.xml. This function extracts both, plus a list of workflow
    files that the solution references.
    """
    out: dict[str, Any] = {"found": False, "connection_references": [], "workflows": []}
    candidates = list(root.glob("**/customizations.xml"))
    if not candidates:
        return out

    path = candidates[0]
    out["found"] = True
    out["path"] = str(path)
    try:
        tree = ET.parse(path)
        xml_root = tree.getroot()
    except Exception as exc:  # noqa: BLE001
        out["parse_error"] = str(exc)
        return out

    # <connectionreferences> block (note: lowercase tag in Dataverse XML)
    for cref in xml_root.iter():
        tag = cref.tag.split("}")[-1].lower()
        if tag != "connectionreference":
            continue
        entry = {
            "logical_name": cref.attrib.get("connectionreferencelogicalname"),
            "display_name": None,
            "connector_id": cref.attrib.get("connectorid"),
        }
        # Display name is sometimes nested in a child element
        for child in cref.iter():
            ct = child.tag.split("}")[-1].lower()
            if ct == "connectionreferencedisplayname" and child.text:
                entry["display_name"] = child.text.strip()
        if entry["logical_name"] or entry["connector_id"]:
            out["connection_references"].append(entry)

    # Workflows list inside customizations.xml
    for wf in xml_root.iter():
        tag = wf.tag.split("}")[-1].lower()
        if tag != "workflow":
            continue
        wf_entry = {
            "schema_name": wf.attrib.get("WorkflowId") or wf.attrib.get("Name"),
            "name": wf.attrib.get("Name"),
            "json_file": None,
        }
        for child in wf.iter():
            ct = child.tag.split("}")[-1].lower()
            if ct == "jsonfilename" and child.text:
                wf_entry["json_file"] = child.text.strip()
        out["workflows"].append(wf_entry)

    return out


def _parse_connection_references(root: Path, customizations: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect connection references from three locations:

    1. Top-level ``connectionreferences/`` folder (older solution shape).
    2. ``<connectionreferences>`` block inside ``customizations.xml`` (modern shape).
    3. ``connectionReferences`` properties inside each workflow JSON under ``Workflows/``.

    Duplicates are de-duplicated by logical name.
    """
    by_name: dict[str, dict[str, Any]] = {}

    # 1. Folder-based (older shape)
    base = _find_folder(root, "connectionreferences")
    if base is not None:
        for xml_file in base.rglob("*.xml"):
            try:
                tree = ET.parse(xml_file)
                xml_root = tree.getroot()
                ln = _xml_text(xml_root, ".//connectionreferencelogicalname")
                entry = {
                    "source": "connectionreferences/",
                    "file": str(xml_file.relative_to(root)),
                    "logical_name": ln,
                    "display_name": _xml_text(xml_root, ".//connectionreferencedisplayname"),
                    "connector_id": _xml_text(xml_root, ".//connectorid"),
                }
                key = ln or entry["file"]
                by_name.setdefault(key, entry)
            except Exception:  # noqa: BLE001
                continue

    # 2. customizations.xml
    for entry in (customizations.get("connection_references") or []):
        ln = entry.get("logical_name")
        key = ln or f"connector:{entry.get('connector_id')}"
        merged = dict(entry)
        merged["source"] = "customizations.xml"
        by_name.setdefault(key, merged)

    # 3. Workflow JSON inline
    wf_dir = _find_folder(root, "Workflows") or _find_folder(root, "workflows")
    if wf_dir is not None:
        for js in wf_dir.rglob("*.json"):
            try:
                data = json.loads(js.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            crefs = _walk_for_key(data, "connectionReferences") or {}
            if isinstance(crefs, dict):
                for slot_name, slot in crefs.items():
                    if not isinstance(slot, dict):
                        continue
                    conn = slot.get("connection") or {}
                    ln = (conn.get("connectionReferenceLogicalName")
                          if isinstance(conn, dict) else None)
                    api = slot.get("api") or {}
                    connector = api.get("name") if isinstance(api, dict) else None
                    key = ln or f"{js.name}:{slot_name}"
                    by_name.setdefault(key, {
                        "source": f"workflow:{js.name}",
                        "logical_name": ln,
                        "connector_id": connector,
                        "slot": slot_name,
                    })

    return list(by_name.values())


def _parse_environment_variables(root: Path) -> list[dict[str, Any]]:
    """Environment variables under environmentvariabledefinitions/."""
    vars_: list[dict[str, Any]] = []
    base = _find_folder(root, "environmentvariabledefinitions")
    if base is None:
        return vars_

    for xml_file in base.rglob("*.xml"):
        try:
            tree = ET.parse(xml_file)
            xml_root = tree.getroot()
            schema_name = (
                _xml_text(xml_root, ".//schemaname")
                or xml_root.attrib.get("schemaname")
            )
            display_name = (
                _xml_text(xml_root, ".//displayname")
                or (xml_root.find(".//displayname").attrib.get("default")
                    if xml_root.find(".//displayname") is not None else None)
            )
            vars_.append(
                {
                    "file": str(xml_file.relative_to(root)),
                    "schema_name": schema_name,
                    "display_name": display_name,
                    "type": _xml_text(xml_root, ".//type"),
                }
            )
        except Exception:  # noqa: BLE001
            vars_.append({"file": str(xml_file.relative_to(root)), "parse_error": True})

    return vars_


def _parse_bots(root: Path) -> list[dict[str, Any]]:
    """Walk the bots/ folder. Each bot lives in its own subfolder.

    Modern Copilot Studio: bot.xml in bots/<schemaname>/, with topic and gpt component
    data under botcomponents/<schemaname>.* sibling folders. Legacy PVA fits the same
    walk via the fallback YAML/JSON harvest.
    """
    bots: list[dict[str, Any]] = []
    base = _find_folder(root, "bots") or _find_folder(root, "bot")
    if base is None:
        return bots

    botcomponents_dir = _find_folder(root, "botcomponents")

    for bot_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        bots.append(_parse_single_bot(bot_dir, root, botcomponents_dir))

    return bots


def _parse_single_bot(
    bot_dir: Path,
    repo_root: Path,
    botcomponents_dir: Path | None,
) -> dict[str, Any]:
    """Extract metadata from a single bot folder, including sibling botcomponents."""
    schema_name = bot_dir.name
    bot: dict[str, Any] = {
        "folder": str(bot_dir.relative_to(repo_root)),
        "schema_name": schema_name,
        "name": None,
        "display_name": None,
        "description": None,
        "description_source": None,
        "instructions": None,
        "instructions_source": None,
        "model": None,
        "icon_present": False,
        "icon_hash": None,
        "icon_length": 0,
        "icon_source": None,
        "telemetry_app_insights_key": None,
        "telemetry_in_export": False,  # whether telemetry is exportable for this agent type
        "suggested_prompts": [],
        "topics": [],
        "system_topics": [],
        "user_topics": [],
        "modified_system_topics": [],
        "gpt_components": [],
        "raw_text_for_judge": "",
    }

    text_chunks: list[str] = []

    # ---- bots/<schema>/ files (bot.xml, configuration.json, etc.) ----
    for yml in list(bot_dir.glob("*.yaml")) + list(bot_dir.glob("*.yml")):
        try:
            data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
            _harvest(data, bot, text_chunks, source=yml.name)
        except Exception:  # noqa: BLE001
            pass

    for js in bot_dir.glob("*.json"):
        try:
            data = json.loads(js.read_text(encoding="utf-8"))
            _harvest(data, bot, text_chunks, source=js.name)
        except Exception:  # noqa: BLE001
            pass

    for xml_file in bot_dir.rglob("*.xml"):
        _harvest_xml(xml_file, bot, text_chunks, source=xml_file.name)

    # ---- botcomponents/<schema>.* sibling folders ----
    if botcomponents_dir is not None:
        prefix_lc = f"{schema_name}.".lower()
        for comp_dir in sorted(botcomponents_dir.iterdir()):
            if not comp_dir.is_dir():
                continue
            if not comp_dir.name.lower().startswith(prefix_lc):
                continue
            comp_name = comp_dir.name[len(schema_name) + 1:]  # part after "<schema>."

            # GPT component carries displayName / description / instructions
            is_gpt = comp_name.lower().startswith("gpt.")
            is_topic = comp_name.lower().startswith("topic.")

            # YAML 'data' file (no extension)
            data_file = comp_dir / "data"
            if data_file.exists():
                try:
                    raw = data_file.read_text(encoding="utf-8")
                    parsed = yaml.safe_load(raw) or {}
                    _harvest(
                        parsed, bot, text_chunks,
                        source=f"botcomponents/{comp_dir.name}/data",
                        is_gpt_component=is_gpt,
                    )
                    if is_gpt:
                        bot["gpt_components"].append(comp_name)
                except Exception:  # noqa: BLE001
                    pass

            # botcomponent.xml carries the agent display name in <name>
            bc_xml = comp_dir / "botcomponent.xml"
            if bc_xml.exists():
                _harvest_xml(
                    bc_xml, bot, text_chunks,
                    source=f"botcomponents/{comp_dir.name}/botcomponent.xml",
                    is_gpt_component=is_gpt,
                )

            if is_topic:
                topic_name = comp_name[len("topic."):]
                bot["topics"].append(topic_name)
                if topic_name in SYSTEM_TOPIC_NAMES:
                    bot["system_topics"].append(topic_name)
                    # Scan the topic's dialog YAML for user customisation.
                    signals = _topic_modification_signals(data_file, schema_name)
                    if signals:
                        bot["modified_system_topics"].append({
                            "name": topic_name,
                            "signals": signals,
                        })
                else:
                    bot["user_topics"].append(topic_name)

    # ---- Fallback: legacy topics folder inside the bot dir ----
    if not bot["topics"]:
        for candidate in ("topics", "components"):
            tf = _find_folder(bot_dir, candidate)
            if tf is not None:
                for topic_file in tf.rglob("*.yaml"):
                    bot["topics"].append(topic_file.stem)
                for topic_file in tf.rglob("*.yml"):
                    bot["topics"].append(topic_file.stem)
                if not bot["topics"]:
                    for topic_file in tf.rglob("*.xml"):
                        bot["topics"].append(topic_file.stem)
                for topic_name in bot["topics"]:
                    if topic_name in SYSTEM_TOPIC_NAMES:
                        bot["system_topics"].append(topic_name)
                    else:
                        bot["user_topics"].append(topic_name)
                break

    icon_exts = (".png", ".svg", ".jpg", ".jpeg", ".ico")
    for p in bot_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in icon_exts:
            bot["icon_present"] = True
            bot["icon_source"] = str(p.relative_to(repo_root))
            try:
                raw = p.read_bytes()
                import hashlib
                bot["icon_hash"] = hashlib.sha256(raw).hexdigest()
                bot["icon_length"] = len(raw)
            except Exception:  # noqa: BLE001
                pass
            break

    # iconbase64 inside bot.xml — also fingerprint so we can compare against
    # known Copilot Studio defaults.
    if not bot["icon_hash"]:
        for xml_file in bot_dir.rglob("*.xml"):
            try:
                text = xml_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue
            match = re.search(r"<iconbase64>([^<]+)</iconbase64>", text, re.IGNORECASE)
            if not match:
                continue
            icon_b64 = match.group(1).strip()
            if icon_b64:
                import hashlib
                bot["icon_present"] = True
                bot["icon_hash"] = hashlib.sha256(icon_b64.encode("utf-8")).hexdigest()
                bot["icon_length"] = len(icon_b64)
                bot["icon_source"] = str(xml_file.relative_to(repo_root))
                break

    bot["raw_text_for_judge"] = "\n\n".join(text_chunks)[:12000]
    return bot


def _harvest_xml(
    xml_file: Path,
    bot: dict[str, Any],
    chunks: list[str],
    *,
    source: str = "",
    is_gpt_component: bool = False,
) -> None:
    """Pull bot-level fields out of an XML file (bot.xml or botcomponent.xml)."""
    try:
        tree = ET.parse(xml_file)
        xml_root = tree.getroot()
    except Exception:  # noqa: BLE001
        return

    # Display name lives in <name> in both bot.xml and botcomponent.xml
    name_val = _xml_text(xml_root, ".//name") or _xml_text(xml_root, "./name")
    if name_val:
        _set_if_empty(bot, "display_name", name_val)
        if is_gpt_component:
            chunks.append(f"[name] {name_val}")

    # Other candidate fields — keep them around for the LLM judge
    for tag in ("displayname", "description", "instructions",
                "additionaldetails", "customgptdescription"):
        val = _xml_text(xml_root, f".//{tag}")
        if val:
            key = "display_name" if tag == "displayname" else tag
            _set_if_empty(bot, key, val)
            if key == "description":
                bot.setdefault("description_source", source)
            if key == "instructions":
                bot.setdefault("instructions_source", source)
            chunks.append(f"[{tag}] {val[:500]}")

    ai_key = (_xml_text(xml_root, ".//applicationinsightsinstrumentationkey")
              or _xml_text(xml_root, ".//applicationinsightsconnectionstring"))
    if ai_key and not bot["telemetry_app_insights_key"]:
        bot["telemetry_app_insights_key"] = ai_key


def _harvest(
    data: Any,
    bot: dict[str, Any],
    chunks: list[str],
    *,
    source: str = "",
    is_gpt_component: bool = False,
) -> None:
    """Recursively scan a parsed YAML/JSON tree for bot fields we care about."""
    if isinstance(data, dict):
        for k, v in data.items():
            kl = str(k).lower()
            if kl in {"displayname", "display_name"} and isinstance(v, str):
                _set_if_empty(bot, "display_name", v)
            elif kl == "name" and isinstance(v, str) and is_gpt_component:
                _set_if_empty(bot, "display_name", v)
            elif kl == "description" and isinstance(v, str):
                _set_if_empty(bot, "description", v)
                bot.setdefault("description_source", source)
                chunks.append(f"[description] {v[:600]}")
            elif kl in {"instructions", "additionaldetails", "additional_details",
                        "persona", "customgptdescription", "customgpt_description"} \
                    and isinstance(v, str):
                if v.strip():
                    _set_if_empty(bot, "instructions", v)
                    bot.setdefault("instructions_source", source)
                    chunks.append(f"[instructions] {v[:1500]}")
            elif kl in {"model", "modelname", "model_name", "aimodel",
                         "modelnamehint", "model_name_hint", "modelhint"} \
                    and isinstance(v, str):
                _set_if_empty(bot, "model", v)
            elif kl in {"suggestedprompts", "suggested_prompts", "conversationstarters"} \
                    and isinstance(v, list):
                bot["suggested_prompts"].extend(str(s)[:200] for s in v)
            elif kl in {"applicationinsightskey", "applicationinsightsinstrumentationkey",
                        "applicationinsightsconnectionstring", "appinsightskey"} \
                    and isinstance(v, str):
                _set_if_empty(bot, "telemetry_app_insights_key", v)
            else:
                _harvest(v, bot, chunks, source=source, is_gpt_component=is_gpt_component)
    elif isinstance(data, list):
        for item in data:
            _harvest(item, bot, chunks, source=source, is_gpt_component=is_gpt_component)


def _walk_for_key(data: Any, target_key: str) -> Any:
    """Find the first occurrence of ``target_key`` anywhere in a parsed JSON/YAML tree."""
    if isinstance(data, dict):
        if target_key in data:
            return data[target_key]
        for v in data.values():
            found = _walk_for_key(v, target_key)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _walk_for_key(item, target_key)
            if found is not None:
                return found
    return None


def _topic_modification_signals(data_file: Path, bot_schema: str) -> list[str]:
    """Return a list of human-readable customisation signals found in a topic's
    dialog YAML. An empty list means the topic looks like a stock system topic.

    Detection is heuristic — it errs on the side of flagging modifications.
    The signals scanned for are things default system topics never contain:
    env-var references, Power Automate / connector / skill calls, generative-
    answer actions, Power Fx Global variables, HTTP requests, or BeginDialog
    into a non-system topic owned by this bot.
    """
    if not data_file.exists():
        return []
    try:
        text = data_file.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return []

    signals: list[str] = []
    for pattern, label in _TOPIC_MOD_SIGNALS:
        if re.search(pattern, text):
            signals.append(label)

    # BeginDialog into a non-system topic owned by this bot is a strong signal.
    # The Fallback default dialog jumps to Escalate (a system topic), so we
    # only flag jumps to topics that are NOT in SYSTEM_TOPIC_NAMES.
    prefix_pat = re.escape(bot_schema) + r"\.topic\.([\w]+)"
    for match in re.finditer(prefix_pat, text):
        target = match.group(1)
        if target not in SYSTEM_TOPIC_NAMES:
            signals.append(f"calls user topic '{target}'")
            break

    # De-duplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for s in signals:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    return ordered


def _set_if_empty(bot: dict[str, Any], key: str, value: str) -> None:
    if not bot.get(key):
        bot[key] = value


def _find_folder(root: Path, name: str) -> Path | None:
    name_lc = name.lower()
    for p in root.rglob("*"):
        if p.is_dir() and p.name.lower() == name_lc:
            return p
    return None


def _xml_text(node: ET.Element, xpath: str) -> str | None:
    found = node.find(xpath)
    if found is not None and found.text:
        return found.text.strip()
    tail = xpath.split("/")[-1].lower().lstrip("./")
    for sibling in node.iter():
        if sibling.tag.split("}")[-1].lower() == tail:
            if sibling.text and sibling.text.strip():
                return sibling.text.strip()
    return None


_INSTRUCTION_KEYWORDS = re.compile(r"\binstructions?\b", re.IGNORECASE)
