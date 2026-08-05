"""Scorecard writers.

Emits three files per run, all timestamped:

* ``scorecard_<solution>_<ts>.md``   — Markdown for git-friendly diffs and ADO Repos preview.
* ``scorecard_<solution>_<ts>.html`` — Visually rich dashboard with inline SVG charts.
  No external CSS/JS — works offline, opens in any browser, safe to email or
  embed in SharePoint.
* ``scorecard_<solution>_<ts>.json`` — Machine-readable payload with a stable,
  versioned schema. Ingested by the Power BI report in quality/powerbi/.

All three files are timestamped in their filename AND in the document body, so a
build history of scorecards is preserved per run.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .static_rules import ScanResult

# Bump when the JSON shape changes in a non-additive way.
SCHEMA_VERSION = 1
SCANNER_VERSION = "1.0.0"


SEVERITY_ORDER = ("blocker", "major", "minor", "info")
SEVERITY_COLORS = {
    "blocker": "#E63946",
    "major": "#F4A261",
    "minor": "#E9C46A",
    "info": "#8AB0AB",
}
STATUS_COLORS = {
    "pass": "#2A9D8F",
    "fail": "#E63946",
    "skipped": "#8D99AE",
}
GRADE_COLORS = {
    "A": "#2A9D8F",
    "B": "#52B788",
    "C": "#E9C46A",
    "D": "#F4A261",
    "F": "#E63946",
}


def write_scorecard(
    result: ScanResult,
    judge_results: dict[str, dict[str, Any] | None],
    *,
    solution_name: str,
    repo_root: Path,
    report_folder: str,
    timestamp: datetime,
    build_number: str | None = None,
) -> Path:
    """Write markdown, HTML, and JSON scorecards. Returns the markdown path (primary)."""
    ts_file = timestamp.strftime("%Y%m%d_%H%M%S")
    ts_display = timestamp.strftime("%Y-%m-%d %H:%M:%S %Z").strip() or timestamp.isoformat()

    folder = repo_root / report_folder
    folder.mkdir(parents=True, exist_ok=True)

    md_path = folder / f"scorecard_{solution_name}_{ts_file}.md"
    html_path = folder / f"scorecard_{solution_name}_{ts_file}.html"
    json_path = folder / f"scorecard_{solution_name}_{ts_file}.json"

    md_path.write_text(
        _render_markdown(
            result, judge_results,
            solution_name=solution_name, ts_display=ts_display, build_number=build_number,
            html_filename=html_path.name,
        ),
        encoding="utf-8",
    )
    html_path.write_text(
        _render_html(
            result, judge_results,
            solution_name=solution_name, ts_display=ts_display, build_number=build_number,
        ),
        encoding="utf-8",
    )
    json_path.write_text(
        _render_json(
            result, judge_results,
            solution_name=solution_name, timestamp=timestamp, build_number=build_number,
        ),
        encoding="utf-8",
    )
    return md_path


# ---------------------------------------------------------------------------
# JSON rendering (Power BI ingestion)
# ---------------------------------------------------------------------------

def _render_json(
    result: ScanResult,
    judge_results: dict[str, dict[str, Any] | None],
    *,
    solution_name: str,
    timestamp: datetime,
    build_number: str | None,
) -> str:
    counts = _count_by_status(result)
    failures_by_sev = _failures_by_severity(result)
    deductions = sum(f.weight for f in result.findings)
    manual_review_count = sum(1 for f in result.findings if f.manual_review)

    findings = []
    for f in result.findings:
        findings.append({
            "rule_id": f.rule_id,
            "name": f.name,
            "severity": f.severity,
            "status": f.status,
            "scope": f.scope,
            "scope_type": "bot" if f.scope.startswith("bot:") else "solution",
            "agent_name": f.scope[4:] if f.scope.startswith("bot:") else None,
            "details": f.details,
            "pp_reference": f.pp_reference,
            "weight_if_failed": _severity_weight(f.severity),
            "deduction": f.weight,
            "manual_review": f.manual_review,
        })

    agents = []
    for bot_name, verdict in (judge_results or {}).items():
        agent_entry: dict[str, Any] = {
            "agent_name": bot_name,
            "judged": False,
            "skipped_reason": None,
            "error": None,
            "clarity": None,
            "scope_discipline": None,
            "persona_defined": None,
            "orchestrator_pattern_detected": None,
            "child_pattern_detected": None,
            "output_format_guidance": None,
            "summary": None,
            "top_strengths": [],
            "top_weaknesses": [],
            "recommended_changes": [],
        }
        if verdict is None:
            agent_entry["skipped_reason"] = "credentials_missing"
        elif verdict.get("skipped"):
            agent_entry["skipped_reason"] = verdict.get("reason", "unknown")
        elif verdict.get("error"):
            agent_entry["error"] = str(verdict.get("error"))
        else:
            agent_entry["judged"] = True
            agent_entry["clarity"] = verdict.get("clarity")
            agent_entry["scope_discipline"] = verdict.get("scope_discipline")
            agent_entry["persona_defined"] = verdict.get("persona_defined")
            agent_entry["orchestrator_pattern_detected"] = verdict.get("orchestrator_pattern_detected")
            agent_entry["child_pattern_detected"] = verdict.get("child_pattern_detected")
            agent_entry["output_format_guidance"] = verdict.get("output_format_guidance")
            agent_entry["summary"] = verdict.get("summary")
            agent_entry["top_strengths"] = list(verdict.get("top_strengths") or [])
            agent_entry["top_weaknesses"] = list(verdict.get("top_weaknesses") or [])
            agent_entry["recommended_changes"] = list(verdict.get("recommended_changes") or [])
        agents.append(agent_entry)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "scanner_version": SCANNER_VERSION,
        "solution_name": solution_name,
        "build_number": build_number,
        "timestamp_utc": timestamp.astimezone().utcnow().isoformat() + "Z" if timestamp.tzinfo is None else timestamp.astimezone().isoformat(),
        "timestamp_local": timestamp.strftime("%Y-%m-%d %H:%M:%S %Z").strip() or timestamp.isoformat(),
        "score": result.score,
        "grade": result.grade,
        "deductions": deductions,
        "summary": {
            "total": len(result.findings),
            "passed": counts["pass"],
            "failed": counts["fail"],
            "skipped": counts["skipped"],
            "manual_review": manual_review_count,
            "failures_by_severity": {
                sev: failures_by_sev.get(sev, 0) for sev in SEVERITY_ORDER
            },
            "agents_total": len(judge_results or {}),
            "agents_judged": _judged_count(judge_results or {}),
        },
        "findings": findings,
        "agents": agents,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _severity_weight(severity: str) -> int:
    from .static_rules import SEVERITY_WEIGHTS
    return SEVERITY_WEIGHTS.get(severity, 0)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _render_markdown(
    result: ScanResult,
    judge_results: dict[str, dict[str, Any] | None],
    *,
    solution_name: str,
    ts_display: str,
    build_number: str | None,
    html_filename: str,
) -> str:
    counts = _count_by_status(result)
    md: list[str] = []
    md.append("# Copilot Studio Agent Quality Scorecard")
    md.append("")
    md.append(f"> A richer visual version of this scorecard is also published as **`{html_filename}`** in this folder.")
    md.append("")
    md.append(f"- **Solution:** {solution_name}")
    md.append(f"- **Generated:** {ts_display}")
    if build_number:
        md.append(f"- **Build:** {build_number}")
    md.append(f"- **Overall Score:** **{result.score} / 100** (grade **{result.grade}**)")
    md.append("")

    manual_review_findings = [f for f in result.findings if f.manual_review]

    md.append("## Summary")
    md.append("")
    md.append(f"- Passed: **{counts['pass']}**")
    md.append(f"- Failed: **{counts['fail']}**")
    md.append(f"- Skipped (insufficient data): **{counts['skipped']}**")
    md.append(f"- Manual review (not scored): **{len(manual_review_findings)}**")
    md.append("")
    md.append(_severity_table(result))
    md.append("")

    md.append("## Static Analysis")
    md.append("")
    md.append(
        "> Rows marked **🔍 manual review** describe P&P items that aren't fully "
        "carried by the solution export. They don't add or remove points from "
        "the score — a human reviewer must verify them in Copilot Studio."
    )
    md.append("")
    md.append("| Rule | Severity | Status | Scope | Details | P&P Reference |")
    md.append("|------|----------|--------|-------|---------|---------------|")
    for f in result.findings:
        status_cell = _status_label(f.status)
        if f.manual_review:
            status_cell = f"{status_cell} · 🔍 manual review"
        md.append(
            f"| {f.rule_id} | {f.severity} | {status_cell} | {f.scope} | "
            f"{_escape_md(f.details)} | {f.pp_reference} |"
        )
    md.append("")

    if manual_review_findings:
        md.append("## Manual Review (Not Scored)")
        md.append("")
        md.append(
            "These checks correspond to P&P guidance that the solution package "
            "doesn't fully carry. The scanner has surfaced them for a human "
            "reviewer — they contribute **0 points** to the score."
        )
        md.append("")
        md.append("| Rule | Scope | What to verify in Copilot Studio | P&P Reference |")
        md.append("|------|-------|----------------------------------|---------------|")
        for f in manual_review_findings:
            md.append(
                f"| {f.rule_id} — {f.name} | {f.scope} | "
                f"{_escape_md(f.details)} | {f.pp_reference} |"
            )
        md.append("")

    if judge_results:
        md.append("## LLM Judge — Instruction Quality")
        md.append("")
        for bot_name, verdict in judge_results.items():
            md.append(f"### Agent: {bot_name}")
            md.append("")
            if verdict is None:
                md.append("_LLM judge skipped — Foundry credentials not configured for this run._")
                md.append("")
                continue
            if verdict.get("skipped"):
                md.append(f"_Skipped: {verdict.get('reason', 'unknown reason')}_")
                md.append("")
                continue
            if verdict.get("error"):
                md.append(f"_Judge call failed: `{verdict['error']}`_")
                md.append("")
                continue

            md.append("| Rubric | Score / Value |")
            md.append("|--------|---------------|")
            md.append(f"| Clarity (0–5) | {verdict.get('clarity', '—')} |")
            md.append(f"| Persona defined | {verdict.get('persona_defined', '—')} |")
            md.append(f"| Scope discipline (0–5) | {verdict.get('scope_discipline', '—')} |")
            md.append(f"| Orchestrator pattern detected | {verdict.get('orchestrator_pattern_detected', '—')} |")
            md.append(f"| Child-agent pattern detected | {verdict.get('child_pattern_detected', '—')} |")
            md.append(f"| Output-format guidance | {verdict.get('output_format_guidance', '—')} |")
            md.append("")
            if verdict.get("summary"):
                md.append(f"**Summary:** {verdict['summary']}")
                md.append("")
            md.append(_bullets("Top strengths", verdict.get("top_strengths", [])))
            md.append(_bullets("Top weaknesses", verdict.get("top_weaknesses", [])))
            md.append(_bullets("Recommended changes", verdict.get("recommended_changes", [])))
            md.append("")

    md.append("---")
    md.append("")
    md.append("_Generated by the Copilot Studio Agent Quality Scanner (MVP)._ ")
    md.append("_Static-rule severities: blocker=10, major=5, minor=2, info=0. Score = 100 − deductions._ ")
    return "\n".join(md)


# ---------------------------------------------------------------------------
# HTML rendering (inline SVG, no external deps)
# ---------------------------------------------------------------------------

def _render_html(
    result: ScanResult,
    judge_results: dict[str, dict[str, Any] | None],
    *,
    solution_name: str,
    ts_display: str,
    build_number: str | None,
) -> str:
    counts = _count_by_status(result)
    failures_by_sev = _failures_by_severity(result)
    grade_color = GRADE_COLORS.get(result.grade, "#8D99AE")
    manual_review_findings = [f for f in result.findings if f.manual_review]
    manual_review_count = len(manual_review_findings)

    score_gauge = _svg_score_gauge(result.score, grade_color)
    status_donut = _svg_donut(
        [
            ("Passed", counts["pass"], STATUS_COLORS["pass"]),
            ("Failed", counts["fail"], STATUS_COLORS["fail"]),
            ("Skipped", counts["skipped"], STATUS_COLORS["skipped"]),
        ],
        size=240,
    )
    severity_bars = _svg_severity_bars(failures_by_sev)

    build_line = f"<span class='meta-chip'>Build {html.escape(build_number)}</span>" if build_number else ""

    parts: list[str] = []
    parts.append(_html_head(solution_name))
    parts.append("<body>")
    parts.append("<div class='wrap'>")

    # Hero -----------------------------------------------------------------
    parts.append("<header class='hero'>")
    parts.append("<div class='hero-text'>")
    parts.append("<div class='eyebrow'>Copilot Studio Agent Quality Scorecard</div>")
    parts.append(f"<h1>{html.escape(solution_name)}</h1>")
    parts.append("<div class='meta'>")
    parts.append(f"<span class='meta-chip'>{html.escape(ts_display)}</span>")
    parts.append(build_line)
    parts.append("</div>")
    parts.append("</div>")
    parts.append("<div class='hero-score'>")
    parts.append(score_gauge)
    parts.append(f"<div class='grade-badge' style='background:{grade_color}'>Grade {html.escape(result.grade)}</div>")
    parts.append("</div>")
    parts.append("</header>")

    # KPI row --------------------------------------------------------------
    parts.append("<section class='kpis'>")
    parts.append(_kpi_card("Passed", counts["pass"], STATUS_COLORS["pass"]))
    parts.append(_kpi_card("Failed", counts["fail"], STATUS_COLORS["fail"]))
    parts.append(_kpi_card("Skipped", counts["skipped"], STATUS_COLORS["skipped"]))
    parts.append(_kpi_card("Manual review", manual_review_count, "#6C63FF"))
    parts.append(_kpi_card("Agents judged", _judged_count(judge_results), "#1E2761"))
    parts.append("</section>")

    # Charts row -----------------------------------------------------------
    parts.append("<section class='charts'>")
    parts.append("<div class='chart-card'>")
    parts.append("<h3>Rule outcomes</h3>")
    parts.append(status_donut)
    parts.append("</div>")
    parts.append("<div class='chart-card'>")
    parts.append("<h3>Failures by severity</h3>")
    parts.append(severity_bars)
    parts.append("</div>")
    parts.append("</section>")

    # Findings table -------------------------------------------------------
    # Severity sort uses a numeric rank so blocker > major > minor > info.
    severity_rank = {"blocker": 0, "major": 1, "minor": 2, "info": 3}
    status_rank = {"fail": 0, "skipped": 1, "pass": 2}

    parts.append("<section class='findings'>")
    parts.append("<h2>Static analysis</h2>")
    parts.append("<div class='table-toolbar'>")
    parts.append(
        "<input type='search' id='findings-filter' class='filter-input' "
        "placeholder='Filter findings (rule, scope, details…)' aria-label='Filter findings'>"
    )
    parts.append("<div class='status-filters' role='group' aria-label='Filter by status'>")
    for label, status_value, color in (
        ("All", "all", "#1E2761"),
        ("Failed", "fail", STATUS_COLORS["fail"]),
        ("Skipped", "skipped", STATUS_COLORS["skipped"]),
        ("Passed", "pass", STATUS_COLORS["pass"]),
        ("Manual review", "manual", "#6C63FF"),
    ):
        active = " is-active" if status_value == "all" else ""
        parts.append(
            f"<button type='button' class='status-btn{active}' data-status='{status_value}' "
            f"style='--btn-color:{color}'>{html.escape(label)}</button>"
        )
    parts.append("</div>")
    parts.append("</div>")
    parts.append("<div class='filter-meta' id='filter-meta'></div>")
    parts.append("<table id='findings-table'>")
    parts.append(
        "<thead><tr>"
        "<th data-sort='rule' class='sortable'>Rule</th>"
        "<th data-sort='severity' class='sortable'>Severity</th>"
        "<th data-sort='status' class='sortable'>Status</th>"
        "<th data-sort='scope' class='sortable'>Scope</th>"
        "<th data-sort='details' class='sortable'>Details</th>"
        "<th data-sort='pp' class='sortable'>P&amp;P</th>"
        "</tr></thead><tbody>"
    )
    for f in result.findings:
        sev_color = SEVERITY_COLORS.get(f.severity, "#8D99AE")
        status_color = STATUS_COLORS.get(f.status, "#8D99AE")
        sev_rank_val = severity_rank.get(f.severity, 99)
        stat_rank_val = status_rank.get(f.status, 99)
        manual_pill = (
            "<span class='pill pill-manual' title='Not scored — verify in Copilot Studio'>"
            "manual review</span>"
            if f.manual_review else ""
        )
        parts.append(
            "<tr"
            f" data-rule='{html.escape(f.rule_id.lower())}'"
            f" data-severity='{html.escape(f.severity.lower())}'"
            f" data-severity-rank='{sev_rank_val}'"
            f" data-status='{html.escape(f.status.lower())}'"
            f" data-status-rank='{stat_rank_val}'"
            f" data-manual-review='{'true' if f.manual_review else 'false'}'"
            f" data-scope='{html.escape(f.scope.lower())}'"
            f" data-details='{html.escape((f.details or '').lower())}'"
            f" data-pp='{html.escape((f.pp_reference or '').lower())}'"
            ">"
            f"<td class='mono'>{html.escape(f.rule_id)}<div class='rule-name'>{html.escape(f.name)}</div></td>"
            f"<td><span class='pill' style='background:{sev_color}'>{html.escape(f.severity)}</span></td>"
            f"<td><div class='status-cell'><span class='pill' style='background:{status_color}'>{html.escape(f.status)}</span>{manual_pill}</div></td>"
            f"<td>{html.escape(f.scope)}</td>"
            f"<td>{html.escape(f.details or '')}</td>"
            f"<td class='small'>{html.escape(f.pp_reference)}</td>"
            "</tr>"
        )
    parts.append("</tbody></table>")
    parts.append("<div class='empty-state' id='empty-state' hidden>No findings match the current filter.</div>")
    parts.append("</section>")

    # Manual review (not scored) ------------------------------------------
    if manual_review_findings:
        parts.append("<section class='manual-review'>")
        parts.append("<h2>Manual review <span class='subtitle'>· not scored</span></h2>")
        parts.append(
            "<p class='intro'>These checks correspond to P&amp;P guidance that the "
            "solution package doesn't fully carry. The scanner has surfaced them "
            "for a human reviewer — they contribute <strong>0 points</strong> to the score.</p>"
        )
        parts.append("<table class='manual-table'>")
        parts.append(
            "<thead><tr>"
            "<th>Rule</th><th>Scope</th>"
            "<th>What to verify in Copilot Studio</th><th>P&amp;P</th>"
            "</tr></thead><tbody>"
        )
        for f in manual_review_findings:
            parts.append(
                "<tr>"
                f"<td class='mono'>{html.escape(f.rule_id)}<div class='rule-name'>{html.escape(f.name)}</div></td>"
                f"<td>{html.escape(f.scope)}</td>"
                f"<td>{html.escape(f.details or '')}</td>"
                f"<td class='small'>{html.escape(f.pp_reference)}</td>"
                "</tr>"
            )
        parts.append("</tbody></table>")
        parts.append("</section>")

    # Judge ----------------------------------------------------------------
    if judge_results:
        parts.append("<section class='judge'>")
        parts.append("<h2>LLM judge — instruction quality</h2>")
        for bot_name, verdict in judge_results.items():
            parts.append("<div class='agent-card'>")
            parts.append(f"<h3>{html.escape(bot_name)}</h3>")
            if verdict is None:
                parts.append("<p class='muted'>LLM judge skipped — Foundry credentials not configured for this run.</p>")
            elif verdict.get("skipped"):
                parts.append(f"<p class='muted'>Skipped: {html.escape(str(verdict.get('reason', 'unknown')))}</p>")
            elif verdict.get("error"):
                parts.append(f"<p class='muted'>Judge call failed: <code>{html.escape(str(verdict['error']))}</code></p>")
            else:
                parts.append(_judge_rubric_block(verdict))
                if verdict.get("summary"):
                    parts.append(f"<p class='summary'>{html.escape(str(verdict['summary']))}</p>")
                parts.append(_judge_list_block("Top strengths", verdict.get("top_strengths", []), "#2A9D8F"))
                parts.append(_judge_list_block("Top weaknesses", verdict.get("top_weaknesses", []), "#E63946"))
                parts.append(_judge_list_block("Recommended changes", verdict.get("recommended_changes", []), "#1E2761"))
            parts.append("</div>")
        parts.append("</section>")

    parts.append("<footer>")
    parts.append("<p>Generated by the Copilot Studio Agent Quality Scanner (MVP). ")
    parts.append("Scoring: 100 − sum of failed-rule severities (blocker=10, major=5, minor=2, info=0).</p>")
    parts.append("</footer>")
    parts.append("</div>")
    parts.append(_findings_table_script())
    parts.append("</body></html>")
    return "\n".join(parts)


def _findings_table_script() -> str:
    """Inline JS for sortable/filterable static-analysis table. No external deps."""
    return """<script>
(function () {
  var table = document.getElementById('findings-table');
  if (!table) return;
  var tbody = table.querySelector('tbody');
  var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
  var filterInput = document.getElementById('findings-filter');
  var statusButtons = document.querySelectorAll('.status-btn');
  var meta = document.getElementById('filter-meta');
  var empty = document.getElementById('empty-state');
  var totalRows = rows.length;
  var activeStatus = 'all';
  var sortKey = null;
  var sortDir = 1;

  function getSortValue(row, key) {
    if (key === 'severity') return parseInt(row.dataset.severityRank, 10);
    if (key === 'status') return parseInt(row.dataset.statusRank, 10);
    if (key === 'rule') return row.dataset.rule || '';
    if (key === 'scope') return row.dataset.scope || '';
    if (key === 'details') return row.dataset.details || '';
    if (key === 'pp') return row.dataset.pp || '';
    return '';
  }

  function applyFilter() {
    var q = (filterInput.value || '').toLowerCase().trim();
    var visible = 0;
    rows.forEach(function (row) {
      var matchesStatus;
      if (activeStatus === 'all') {
        matchesStatus = true;
      } else if (activeStatus === 'manual') {
        matchesStatus = row.dataset.manualReview === 'true';
      } else {
        matchesStatus = row.dataset.status === activeStatus;
      }
      var haystack = [
        row.dataset.rule, row.dataset.severity, row.dataset.status,
        row.dataset.scope, row.dataset.details, row.dataset.pp,
        (row.textContent || '').toLowerCase()
      ].join(' ');
      var matchesQuery = !q || haystack.indexOf(q) !== -1;
      var show = matchesStatus && matchesQuery;
      row.classList.toggle('is-hidden', !show);
      if (show) visible++;
    });
    if (meta) {
      if (visible === totalRows && !q && activeStatus === 'all') {
        meta.textContent = 'Showing all ' + totalRows + ' finding' + (totalRows === 1 ? '' : 's') + '.';
      } else {
        meta.textContent = 'Showing ' + visible + ' of ' + totalRows + ' finding' + (totalRows === 1 ? '' : 's') + '.';
      }
    }
    if (empty) empty.hidden = visible !== 0;
  }

  function applySort(key) {
    if (sortKey === key) {
      sortDir = -sortDir;
    } else {
      sortKey = key;
      sortDir = 1;
    }
    var sorted = rows.slice().sort(function (a, b) {
      var av = getSortValue(a, key);
      var bv = getSortValue(b, key);
      if (typeof av === 'number' && typeof bv === 'number') {
        return (av - bv) * sortDir;
      }
      return String(av).localeCompare(String(bv)) * sortDir;
    });
    sorted.forEach(function (r) { tbody.appendChild(r); });
    table.querySelectorAll('th.sortable').forEach(function (th) {
      th.classList.remove('sort-asc', 'sort-desc');
      if (th.dataset.sort === key) {
        th.classList.add(sortDir === 1 ? 'sort-asc' : 'sort-desc');
      }
    });
  }

  table.querySelectorAll('th.sortable').forEach(function (th) {
    th.addEventListener('click', function () { applySort(th.dataset.sort); });
  });

  if (filterInput) {
    filterInput.addEventListener('input', applyFilter);
  }

  statusButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      activeStatus = btn.dataset.status;
      statusButtons.forEach(function (b) { b.classList.toggle('is-active', b === btn); });
      applyFilter();
    });
  });

  applyFilter();
})();
</script>"""


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _html_head(solution_name: str) -> str:
    title = html.escape(f"{solution_name} — Quality Scorecard")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{
    --navy: #1E2761;
    --ice:  #CADCFC;
    --bg:   #F6F8FC;
    --card: #FFFFFF;
    --ink:  #1A1F36;
    --muted:#5B6B86;
    --line: #E5EAF3;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--ink); line-height: 1.5;
  }}
  .wrap {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px 64px; }}
  .hero {{
    background: linear-gradient(135deg, #1E2761 0%, #2D3F8E 100%);
    color: white; border-radius: 16px; padding: 32px 40px;
    display: flex; align-items: center; justify-content: space-between; gap: 32px;
    box-shadow: 0 8px 24px rgba(30,39,97,0.18);
  }}
  .hero h1 {{ margin: 8px 0 12px; font-size: 32px; font-weight: 700; letter-spacing: -0.02em; }}
  .eyebrow {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.12em; color: var(--ice); opacity: 0.85; }}
  .meta {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .meta-chip {{
    display: inline-block; background: rgba(255,255,255,0.14);
    padding: 4px 10px; border-radius: 999px; font-size: 13px;
  }}
  .hero-score {{ display: flex; flex-direction: column; align-items: center; gap: 12px; }}
  .grade-badge {{
    padding: 8px 20px; border-radius: 999px; font-weight: 700;
    color: white; font-size: 18px; letter-spacing: 0.04em;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  }}
  .kpis {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin: 24px 0; }}
  .kpi {{
    background: var(--card); padding: 20px; border-radius: 12px;
    border-left: 4px solid var(--navy);
    box-shadow: 0 2px 6px rgba(30,39,97,0.06);
  }}
  .kpi .label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted); }}
  .kpi .value {{ font-size: 36px; font-weight: 700; line-height: 1.1; margin-top: 4px; }}
  .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
  .chart-card {{
    background: var(--card); padding: 24px; border-radius: 12px;
    box-shadow: 0 2px 6px rgba(30,39,97,0.06);
  }}
  .chart-card h3 {{ margin: 0 0 16px; font-size: 16px; color: var(--navy); }}
  .findings, .judge {{
    background: var(--card); padding: 24px; border-radius: 12px; margin-bottom: 24px;
    box-shadow: 0 2px 6px rgba(30,39,97,0.06);
  }}
  h2 {{ margin: 0 0 16px; color: var(--navy); font-size: 22px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ text-align: left; padding: 10px 12px; background: var(--bg); color: var(--muted);
        font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
        border-bottom: 1px solid var(--line); }}
  td {{ padding: 12px; border-bottom: 1px solid var(--line); vertical-align: top; }}
  tr:last-child td {{ border-bottom: 0; }}
  .pill {{
    display: inline-block; padding: 3px 10px; border-radius: 999px;
    color: white; font-size: 12px; font-weight: 600; text-transform: capitalize;
  }}
  .pill-manual {{
    background: white; color: #6C63FF; border: 1px dashed #6C63FF;
    text-transform: lowercase; letter-spacing: 0.02em;
  }}
  .status-cell {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
  .manual-review {{
    background: var(--card); padding: 24px; border-radius: 12px; margin-bottom: 24px;
    box-shadow: 0 2px 6px rgba(30,39,97,0.06);
    border-left: 4px solid #6C63FF;
  }}
  .manual-review h2 {{ color: #4B45B3; }}
  .manual-review .subtitle {{
    font-size: 13px; font-weight: 500; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.08em; margin-left: 6px;
  }}
  .manual-review .intro {{ color: var(--muted); margin: 0 0 16px; }}
  .manual-table th {{ background: #F2F1FF; color: #4B45B3; }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
           font-size: 13px; font-weight: 600; color: var(--navy); }}
  .rule-name {{ font-family: inherit; font-weight: 400; font-size: 12px; color: var(--muted); margin-top: 2px; }}
  .small {{ font-size: 12px; color: var(--muted); }}
  .muted {{ color: var(--muted); font-style: italic; }}
  .agent-card {{ border: 1px solid var(--line); border-radius: 12px; padding: 20px; margin-bottom: 16px; }}
  .agent-card h3 {{ margin: 0 0 16px; color: var(--navy); }}
  .rubric {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }}
  .rubric-item {{ background: var(--bg); border-radius: 8px; padding: 12px; }}
  .rubric-item .lbl {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }}
  .rubric-item .val {{ font-size: 20px; font-weight: 700; color: var(--navy); }}
  .bar-track {{ background: var(--line); border-radius: 4px; height: 6px; margin-top: 8px; overflow: hidden; }}
  .bar-fill {{ height: 100%; background: var(--navy); border-radius: 4px; }}
  .summary {{ background: var(--bg); padding: 12px 16px; border-left: 3px solid var(--navy); border-radius: 4px; }}
  .judge-list {{ margin: 12px 0; }}
  .judge-list h4 {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; margin: 0 0 6px; }}
  .judge-list ul {{ margin: 0; padding-left: 20px; }}
  .judge-list li {{ margin-bottom: 4px; }}
  .table-toolbar {{
    display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
    margin: 4px 0 12px;
  }}
  .filter-input {{
    flex: 1; min-width: 220px; padding: 8px 12px;
    border: 1px solid var(--line); border-radius: 8px;
    font-size: 14px; font-family: inherit; color: var(--ink);
    background: var(--bg);
  }}
  .filter-input:focus {{ outline: 2px solid var(--navy); outline-offset: 0; background: white; }}
  .status-filters {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .status-btn {{
    --btn-color: var(--navy);
    border: 1px solid var(--line); background: white; color: var(--muted);
    padding: 6px 12px; border-radius: 999px;
    font-size: 12px; font-weight: 600; cursor: pointer;
    text-transform: uppercase; letter-spacing: 0.06em;
    transition: all 120ms ease;
  }}
  .status-btn:hover {{ border-color: var(--btn-color); color: var(--btn-color); }}
  .status-btn.is-active {{
    background: var(--btn-color); color: white; border-color: var(--btn-color);
  }}
  .filter-meta {{
    font-size: 12px; color: var(--muted); margin-bottom: 8px; min-height: 16px;
  }}
  th.sortable {{ cursor: pointer; user-select: none; position: relative; padding-right: 22px; }}
  th.sortable:hover {{ color: var(--navy); }}
  th.sortable::after {{
    content: '↕'; position: absolute; right: 8px; opacity: 0.35; font-size: 11px;
  }}
  th.sortable.sort-asc::after {{ content: '↑'; opacity: 1; color: var(--navy); }}
  th.sortable.sort-desc::after {{ content: '↓'; opacity: 1; color: var(--navy); }}
  tr.is-hidden {{ display: none; }}
  .empty-state {{
    padding: 24px; text-align: center; color: var(--muted);
    font-style: italic; background: var(--bg); border-radius: 8px; margin-top: 8px;
  }}
  footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--line);
            text-align: center; color: var(--muted); font-size: 12px; }}
  @media (max-width: 1100px) {{
    .kpis {{ grid-template-columns: repeat(3, 1fr); }}
  }}
  @media (max-width: 800px) {{
    .hero {{ flex-direction: column; text-align: center; }}
    .kpis {{ grid-template-columns: repeat(2, 1fr); }}
    .charts {{ grid-template-columns: 1fr; }}
    .rubric {{ grid-template-columns: 1fr; }}
  }}
</style></head>"""


def _kpi_card(label: str, value: int, color: str) -> str:
    return (
        f"<div class='kpi' style='border-left-color:{color}'>"
        f"<div class='label'>{html.escape(label)}</div>"
        f"<div class='value' style='color:{color}'>{value}</div>"
        "</div>"
    )


def _judged_count(judge_results: dict[str, dict[str, Any] | None]) -> int:
    n = 0
    for v in judge_results.values():
        if v is None:
            continue
        if v.get("skipped") or v.get("error"):
            continue
        n += 1
    return n


def _judge_rubric_block(verdict: dict[str, Any]) -> str:
    items = [
        ("Clarity", verdict.get("clarity"), 5),
        ("Scope discipline", verdict.get("scope_discipline"), 5),
        ("Persona defined", _yesno(verdict.get("persona_defined")), None),
        ("Output-format guidance", _yesno(verdict.get("output_format_guidance")), None),
        ("Orchestrator pattern", _yesno(verdict.get("orchestrator_pattern_detected")), None),
        ("Child-agent pattern", _yesno(verdict.get("child_pattern_detected")), None),
    ]
    parts = ["<div class='rubric'>"]
    for label, value, max_value in items:
        display = "—" if value in (None, "") else str(value)
        bar = ""
        if max_value and isinstance(value, (int, float)):
            pct = max(0, min(100, int(value) / max_value * 100))
            bar = f"<div class='bar-track'><div class='bar-fill' style='width:{pct}%'></div></div>"
        parts.append(
            "<div class='rubric-item'>"
            f"<div class='lbl'>{html.escape(label)}</div>"
            f"<div class='val'>{html.escape(display)}</div>"
            f"{bar}</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _judge_list_block(title: str, items: list[str], color: str) -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{html.escape(str(i))}</li>" for i in items)
    return (
        "<div class='judge-list'>"
        f"<h4 style='color:{color}'>{html.escape(title)}</h4>"
        f"<ul>{lis}</ul>"
        "</div>"
    )


def _yesno(value: Any) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "—"


# ---------------------------------------------------------------------------
# Inline SVG charts
# ---------------------------------------------------------------------------

def _svg_score_gauge(score: int, color: str) -> str:
    """Big circular gauge showing score / 100."""
    score = max(0, min(100, int(score)))
    radius = 70
    circumference = 2 * 3.14159 * radius
    dash = circumference * score / 100
    gap = circumference - dash
    size = 180
    cx = cy = size / 2
    return f"""<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
  <circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="rgba(255,255,255,0.18)" stroke-width="14"/>
  <circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{color}" stroke-width="14"
          stroke-dasharray="{dash:.2f} {gap:.2f}" stroke-dashoffset="{circumference/4:.2f}"
          stroke-linecap="round" transform="rotate(-90 {cx} {cy})"/>
  <text x="{cx}" y="{cy - 4}" text-anchor="middle" font-size="42" font-weight="700"
        fill="white" font-family="Segoe UI, sans-serif">{score}</text>
  <text x="{cx}" y="{cy + 22}" text-anchor="middle" font-size="13"
        fill="rgba(255,255,255,0.75)" font-family="Segoe UI, sans-serif" letter-spacing="2">/ 100</text>
</svg>"""


def _svg_donut(slices: list[tuple[str, int, str]], *, size: int = 220) -> str:
    """Donut chart from (label, value, color) tuples with a legend below."""
    total = sum(v for _, v, _ in slices) or 1
    radius = size * 0.35
    inner_radius = radius * 0.6
    cx = cy = size / 2
    paths: list[str] = []
    start_angle = -90.0
    for label, value, color in slices:
        if value <= 0:
            continue
        sweep = 360.0 * value / total
        end_angle = start_angle + sweep
        paths.append(_donut_path(cx, cy, radius, inner_radius, start_angle, end_angle, color))
        start_angle = end_angle

    # Center label
    center_text = (
        f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" font-size="28" font-weight="700"'
        f' fill="#1E2761" font-family="Segoe UI, sans-serif">{total}</text>'
        f'<text x="{cx}" y="{cy + 18}" text-anchor="middle" font-size="11"'
        f' fill="#5B6B86" font-family="Segoe UI, sans-serif" letter-spacing="2">RULES</text>'
    )

    legend_items = []
    for label, value, color in slices:
        pct = (value / total) * 100 if total else 0
        legend_items.append(
            f'<div style="display:flex;align-items:center;gap:8px;margin:6px 0;font-size:13px;">'
            f'<span style="width:12px;height:12px;background:{color};border-radius:3px;display:inline-block;"></span>'
            f'<span style="color:#1A1F36;font-weight:600;">{html.escape(label)}</span>'
            f'<span style="color:#5B6B86;margin-left:auto;">{value} · {pct:.0f}%</span>'
            f'</div>'
        )

    svg = (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">'
        + "".join(paths)
        + center_text
        + "</svg>"
    )
    return (
        '<div style="display:flex;gap:16px;align-items:center;">'
        f'<div>{svg}</div>'
        f'<div style="flex:1;">{"".join(legend_items)}</div>'
        '</div>'
    )


def _donut_path(cx: float, cy: float, r_outer: float, r_inner: float,
                start_angle: float, end_angle: float, color: str) -> str:
    import math
    sa = math.radians(start_angle)
    ea = math.radians(end_angle)
    large_arc = 1 if (end_angle - start_angle) > 180 else 0
    x1, y1 = cx + r_outer * math.cos(sa), cy + r_outer * math.sin(sa)
    x2, y2 = cx + r_outer * math.cos(ea), cy + r_outer * math.sin(ea)
    x3, y3 = cx + r_inner * math.cos(ea), cy + r_inner * math.sin(ea)
    x4, y4 = cx + r_inner * math.cos(sa), cy + r_inner * math.sin(sa)
    d = (
        f"M {x1:.2f} {y1:.2f} "
        f"A {r_outer:.2f} {r_outer:.2f} 0 {large_arc} 1 {x2:.2f} {y2:.2f} "
        f"L {x3:.2f} {y3:.2f} "
        f"A {r_inner:.2f} {r_inner:.2f} 0 {large_arc} 0 {x4:.2f} {y4:.2f} Z"
    )
    return f'<path d="{d}" fill="{color}"/>'


def _svg_severity_bars(by_sev: dict[str, int]) -> str:
    """Horizontal bar chart of failure counts by severity."""
    max_value = max(by_sev.values(), default=0)
    if max_value == 0:
        return (
            '<div style="text-align:center;padding:40px 0;color:#5B6B86;">'
            '<div style="font-size:48px;line-height:1;color:#2A9D8F;">●</div>'
            '<div style="margin-top:8px;font-weight:600;color:#1A1F36;">No failures</div>'
            '<div style="font-size:13px;">All rules passed or were skipped.</div>'
            '</div>'
        )

    width = 360
    bar_h = 28
    gap = 12
    label_w = 80
    rows = []
    for sev in SEVERITY_ORDER:
        count = by_sev.get(sev, 0)
        pct = count / max_value if max_value else 0
        bar_w = max(2, (width - label_w - 50) * pct) if count else 0
        color = SEVERITY_COLORS[sev]
        rows.append(
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:{gap}px;">'
            f'<div style="width:{label_w}px;font-size:13px;font-weight:600;color:#1A1F36;text-transform:capitalize;">{sev}</div>'
            f'<div style="flex:1;background:#F6F8FC;border-radius:4px;height:{bar_h}px;position:relative;">'
            f'<div style="background:{color};height:100%;width:{bar_w}px;border-radius:4px;'
            f'display:flex;align-items:center;padding-left:8px;color:white;font-weight:700;font-size:13px;">'
            f'{count if count else ""}</div>'
            f'</div>'
            f'</div>'
        )
    return "<div>" + "".join(rows) + "</div>"


# ---------------------------------------------------------------------------
# Markdown helpers (existing)
# ---------------------------------------------------------------------------

def _count_by_status(result: ScanResult) -> dict[str, int]:
    out = {"pass": 0, "fail": 0, "skipped": 0}
    for f in result.findings:
        if f.status in out:
            out[f.status] += 1
    return out


def _failures_by_severity(result: ScanResult) -> dict[str, int]:
    by_sev: dict[str, int] = {}
    for f in result.findings:
        if f.status == "fail":
            by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    return by_sev


def _severity_table(result: ScanResult) -> str:
    by_sev = _failures_by_severity(result)
    if not by_sev:
        return "No rule failures detected."
    rows = ["| Severity | Failures |", "|----------|----------|"]
    for sev in SEVERITY_ORDER:
        if sev in by_sev:
            rows.append(f"| {sev} | {by_sev[sev]} |")
    return "\n".join(rows)


def _status_label(status: str) -> str:
    return {"pass": "✅ pass", "fail": "❌ fail", "skipped": "⚪ skipped"}.get(status, status)


def _escape_md(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def _bullets(title: str, items: list[str]) -> str:
    if not items:
        return ""
    out = [f"**{title}:**", ""]
    out.extend(f"- {item}" for item in items)
    out.append("")
    return "\n".join(out)
