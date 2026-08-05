"""Load rule metadata and model/icon config bundled with the engine."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from engine.rule_catalogue import load_rule_catalogue

_ENGINE_DIR = Path(__file__).resolve().parent
RULE_CATALOGUE_PATH = _ENGINE_DIR / "rules" / "rule-catalogue.md"
MODEL_CONFIG_PATH = _ENGINE_DIR / "model_catalogue.yml"

ENGINE_VERSION = "1.0.0"


SEVERITY_WEIGHTS = {"blocker": 10, "major": 5, "minor": 2, "info": 0}

# Which level each rule applies at, and a default human explanation. Used to seed
# the editable RuleConfig table; admins can override the explanation afterwards.
RULE_SCOPE = {
    "SOL-001": "solution", "SOL-002": "solution", "CON-001": "solution", "ENV-001": "solution",
}
DEFAULT_EXPLANATIONS = {
    "SOL-001": "The agent should live in a custom solution with a proper publisher prefix, not the default/system solution.",
    "SOL-002": "The owning solution should carry a non-default version so builds are traceable.",
    "CON-001": "Use connection references rather than hardcoded connections so the solution moves cleanly between environments.",
    "ENV-001": "Parameterise environment-specific values with environment variables instead of hardcoding them.",
    "AGT-001": "Every agent needs a clear display name.",
    "AGT-002": "A meaningful description (50+ chars) helps users and reviewers understand the agent's purpose.",
    "AGT-003": "Substantive instructions (200+ chars) are required for the agent to behave predictably.",
    "AGT-004": "Instructions shouldn't be excessively long (over 8000 chars) — refactor into topics/knowledge.",
    "AGT-005": "The agent should have user-created topics or meaningfully customised system topics.",
    "AGT-006": "Configure at least three suggested prompts to guide users.",
    "AGT-007": "Wire up Application Insights so runs, errors and latency are observable.",
    "AGT-008": "Record a model selection that is GA or the default — avoid preview/experimental/retired models in production.",
    "AGT-009": "Upload a custom, on-theme icon rather than leaving the default Copilot Studio icon.",
}


def default_weight(severity: str) -> int:
    return SEVERITY_WEIGHTS.get(severity.lower(), 0)


@lru_cache
def load_rules() -> list[dict[str, Any]]:
    return load_rule_catalogue(RULE_CATALOGUE_PATH)


@lru_cache
def load_model_config() -> dict[str, Any]:
    return yaml.safe_load(MODEL_CONFIG_PATH.read_text(encoding="utf-8")) or {}


@lru_cache
def catalogue_hash() -> str:
    return hashlib.sha256(
        RULE_CATALOGUE_PATH.read_bytes()
    ).hexdigest()[:12]
