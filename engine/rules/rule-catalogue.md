# Copilot Studio Agent Quality — Rule Catalogue

This file is the **single source of truth** for the static rules applied by the
scanner. Each rule maps back to a specific slide in the *Patterns & Practices
for Copilot Studio agent development* deck so reviewers can trace any finding to
the underlying guidance.

The scanner parses this file at runtime (see `scanner/rule_catalogue.py`). To
change a rule's severity, rename it, or update its P&P reference, edit the
relevant table row below and commit — no Python changes required.

> **Adding a new rule?** The rule's *behaviour* (the check itself) still lives in
> `scanner/static_rules.py`. The metadata in this file (id, name, severity, P&P
> reference) is what the scanner reports — but the actual evaluation logic is
> code. So: add a row here AND add a `Finding(...)` block in `run_static_rules()`
> referencing the same `rule_id`.

## Severity model

| Severity | Weight | Meaning |
|----------|-------:|---------|
| `blocker` | 10 | Agent will not function correctly without this. Always fix before promoting. |
| `major`   | 5  | Significant gap against P&P. Fix before going to production. |
| `minor`   | 2  | Nice-to-have. Acceptable to ship without, but address in the next iteration. |
| `info`    | 0  | Informational only. No score impact. |

**Score formula:** `100 − Σ(weight of each failed rule)`, clamped to `[0, 100]`.
Grade bands: `A ≥ 90`, `B ≥ 75`, `C ≥ 60`, `D ≥ 40`, `F < 40`.

---

## Solution-level rules

These checks run once per solution.

| Rule ID  | Name | Severity | P&P Reference |
|----------|------|----------|---------------|
| `SOL-001` | Publisher prefix is custom (not 'new') | major | Slide 5 - Solutions |
| `SOL-002` | Solution has a non-default version | minor | Slide 5 - Solutions |
| `CON-001` | Connection references are used (no orphaned connections) | major | Slide 6 - Connection References |
| `ENV-001` | Environment variables defined for env-specific values | major | Slide 7 - Environment Variables |

## Per-agent rules

These checks run once per bot/agent detected inside the solution. The
scorecard's `scope` column will read `bot:<agent display name>` for each
finding.

| Rule ID  | Name | Severity | P&P Reference |
|----------|------|----------|---------------|
| `AGT-001` | Agent has a display name | blocker | Slide 12 - Name |
| `AGT-002` | Agent has a meaningful description (>= 50 chars) | major | Slide 14 - Description |
| `AGT-003` | Agent instructions are present (>= 200 chars) | blocker | Slide 17 - Instructions |
| `AGT-004` | Agent instructions are not excessive (<= 8000 chars) | minor | Slide 17 - Instructions |
| `AGT-005` | Agent has user-created topics, or system topics customised by the maker | major | Slide 18 - Topics |
| `AGT-006` | Agent has suggested prompts configured (>= 3) | minor | Slide 19 - Suggested Prompts |
| `AGT-007` | Application Insights telemetry is configured | major | Slide 20 - Telemetry |
| `AGT-008` | Agent model selection is recorded and is GA/default (not preview/experimental/retired) | info | Slide 15 - Model Selection |
| `AGT-009` | Agent has a custom (non-default) icon | minor | Slide 13 - Icon |

## Manual review (not auto-scored)

Some P&P items aren't fully carried by the Dataverse solution export, or the
export only records *presence* rather than *quality*. When the scanner reads a
**static solution ZIP** it lists these rules but flags them as **Manual review** —
they don't add or remove points. A human reviewer must verify them in Copilot
Studio.

> **Live API scanning changes this.** When the platform reads an agent live from
> the **Dataverse Web API** (rather than a ZIP), `AGT-002` becomes a **fully
> scored** pass/fail check because the live rows carry the description that the
> static export drops. `AGT-007` (Application Insights) is a special case: the
> connection is configured in Copilot Studio and **is not exposed on any Dataverse
> table**, so it can never be read from the solution *or* the live API — it stays
> **manual review** unless telemetry is positively observed via the Application
> Insights query API (connect the environment's App Insights in Admin to auto-verify).

| Rule ID  | Why it's manual review |
|----------|------------------------|
| `AGT-002` | Description field isn't present in modern Copilot Studio exports — review the description inside Studio. |
| `AGT-007` | Application Insights configuration is stored outside the solution package — verify telemetry in Studio. |
| `AGT-009` | Triggers manual review only when an icon is present but `icon.known_default_hashes` is empty in `config.yml`. Once you record the default icon's SHA-256 there, AGT-009 becomes a scored pass/fail. |

### AGT-008 — Model selection notes

The scanner reads `aiSettings.model.modelNameHint` from
`botcomponents/<bot>.gpt.default/data` and compares it to the catalogue under
`model.catalogue` in `config.yml`. The catalogue mirrors the public Microsoft
Learn table (*Select a primary AI model for your agent*) and is what tells the
scanner whether a model is `default`, `ga`, `preview`, `experimental`, or
`retired`. When Microsoft promotes or retires models, update `config.yml`
rather than touching scanner code.

`AGT-008` is `info` severity, so it never affects the numeric score — but the
finding status (pass/fail) lights up the scorecard so reviewers see at a glance
when an agent is on an experimental, preview, or retired model.

### AGT-009 — Icon fingerprinting notes

The scanner SHA-256s the icon bytes (from a file under the bot folder, or from
the `<iconbase64>` element in `bot.xml`) and compares against
`icon.known_default_hashes` in `config.yml`. Today the list is empty — to make
AGT-009 self-scoring, create a brand-new agent in Copilot Studio, export the
solution, and add the observed icon hash to that list. Until then AGT-009 falls
back to manual review whenever an icon is present.

---

## Parser format notes

The markdown parser is intentionally strict so the catalogue stays readable:

- Each rule lives in a Markdown table with **exactly** the columns
  `Rule ID | Name | Severity | P&P Reference`.
- The `Rule ID` cell must be a backtick-wrapped identifier matching
  `^[A-Z]{3}-[0-9]{3}$` (e.g. `` `SOL-001` ``).
- `Severity` must be one of `blocker`, `major`, `minor`, `info` (case-insensitive).
- Header rows (separator row `|----|----|...`) and section headings are ignored.
- Rows in any table that doesn't have all four columns are ignored, so adding
  prose tables (like the severity model above) is safe.

This means you can split the catalogue into as many tables as you like (by
category, by lifecycle phase, etc.) — the parser collects rules from every
matching table in document order.
