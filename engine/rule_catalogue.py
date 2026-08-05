"""Load rule metadata from the markdown rule catalogue.

The catalogue (``quality/rules/rule-catalogue.md``) is the single source of
truth for rule IDs, names, severities, and P&P slide references. The rule
*behaviour* still lives in ``static_rules.py`` — this module only parses the
table rows so business reviewers can edit the catalogue without touching code.

Format expected (per row):

    | `RULE-ID` | Human-friendly name | severity | Slide N - Topic |

Anything that doesn't look like a rule row (separator rows, prose tables,
narrative paragraphs) is silently skipped.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

VALID_SEVERITIES = {"blocker", "major", "minor", "info"}
_RULE_ID_RE = re.compile(r"^[A-Z]{3}-[0-9]{3}$")
# The catalogue historically prefixed each reference with "Slide N - ". The slide
# numbers aren't meaningful outside the deck, so we strip them and keep just the
# topic (e.g. "Slide 17 - Instructions" -> "Instructions").
_SLIDE_PREFIX_RE = re.compile(r"^\s*slide\s+\d+\s*[-–—:]\s*", re.IGNORECASE)


def clean_pp_reference(value: str) -> str:
    """Strip a leading 'Slide N - ' prefix, returning just the topic name."""
    return _SLIDE_PREFIX_RE.sub("", value or "").strip()


def load_rule_catalogue(path: Path) -> list[dict[str, Any]]:
    """Parse the markdown rule catalogue and return rule-metadata dicts.

    Each dict has keys ``id``, ``name``, ``severity``, ``pp_reference`` —
    matching the shape ``run_static_rules`` expects from ``config.yml``.
    """
    text = path.read_text(encoding="utf-8")
    rules: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 4:
            continue
        if all(set(c) <= {"-", ":"} for c in cells):
            # Markdown table separator row.
            continue

        rule_id = _strip_backticks(cells[0])
        if not _RULE_ID_RE.match(rule_id):
            continue
        if rule_id in seen_ids:
            raise ValueError(f"Duplicate rule ID in catalogue: {rule_id}")

        name = cells[1]
        severity = cells[2].lower()
        pp_reference = cells[3]

        if severity not in VALID_SEVERITIES:
            raise ValueError(
                f"Rule {rule_id} has invalid severity '{severity}'. "
                f"Must be one of {sorted(VALID_SEVERITIES)}."
            )
        if not name:
            raise ValueError(f"Rule {rule_id} is missing a name.")
        if not pp_reference:
            raise ValueError(f"Rule {rule_id} is missing a P&P reference.")

        rules.append({
            "id": rule_id,
            "name": name,
            "severity": severity,
            "pp_reference": clean_pp_reference(pp_reference),
        })
        seen_ids.add(rule_id)

    if not rules:
        raise ValueError(f"No rules parsed from catalogue: {path}")
    return rules


def _strip_backticks(value: str) -> str:
    return value.strip().strip("`").strip()
