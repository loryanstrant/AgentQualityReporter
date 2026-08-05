import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { RuleItem, cleanPP } from "../api/types";

const SEV_BADGE: Record<string, string> = {
  blocker: "badge badge-blocker",
  major: "badge badge-major",
  minor: "badge badge-minor",
  info: "badge badge-info",
};

// Shared column template so the header and every row align perfectly.
// Inline gridTemplateColumns (not a Tailwind arbitrary class) so it always
// applies regardless of the JIT scanner.
const GRID_STYLE = { gridTemplateColumns: "110px 2fr 72px 84px 3fr 72px" } as const;
const COLS = "grid gap-4 items-start";

export default function RulesPage() {
  const [rules, setRules] = useState<RuleItem[]>([]);
  const [draft, setDraft] = useState<Record<string, Partial<RuleItem>>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = () => api.get<RuleItem[]>("/admin/rules").then(setRules);
  useEffect(() => {
    load().catch((e) => setMsg((e as Error).message));
  }, []);

  const flash = (m: string) => {
    setMsg(m);
    setTimeout(() => setMsg(null), 3000);
  };

  const edit = (id: string, patch: Partial<RuleItem>) =>
    setDraft((d) => ({ ...d, [id]: { ...d[id], ...patch } }));

  const save = async (r: RuleItem) => {
    const d = draft[r.rule_id];
    if (!d) return;
    setBusy(r.rule_id);
    try {
      await api.put(`/admin/rules/${r.rule_id}`, {
        enabled: d.enabled ?? r.enabled,
        weight: d.weight ?? r.weight,
        explanation: d.explanation ?? r.explanation,
      });
      setDraft((x) => {
        const n = { ...x };
        delete n[r.rule_id];
        return n;
      });
      await load();
      flash(`${r.rule_id} saved.`);
    } catch (e) {
      flash((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const val = <K extends keyof RuleItem>(r: RuleItem, k: K): RuleItem[K] =>
    (draft[r.rule_id]?.[k] ?? r[k]) as RuleItem[K];
  const dirty = (r: RuleItem) => !!draft[r.rule_id];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-ink">Rules</h2>
          <p className="text-sm text-slate">
            Enable/disable rules, adjust scoring weights, and edit explanations. Changes apply to the
            next scan.
          </p>
        </div>
        <Link to="/settings" className="text-sm text-orange hover:underline">
          ← Back to Admin
        </Link>
      </div>

      {msg && <div className="card p-3 text-sm text-ink border-l-4 border-orange">{msg}</div>}

      <div className="card overflow-x-auto">
        <div className="min-w-[900px]">
          {/* Header row */}
          <div
            style={GRID_STYLE}
            className={`${COLS} px-5 py-3 border-b border-line text-xs font-semibold uppercase tracking-wide text-slate`}
          >
            <div>Rule</div>
            <div>Check</div>
            <div className="text-center">Enabled</div>
            <div className="text-center">Weight</div>
            <div>Explanation</div>
            <div className="text-right">Action</div>
          </div>

          {/* Data rows */}
          {rules.map((r) => (
            <div
              key={r.rule_id}
              style={GRID_STYLE}
              className={`${COLS} px-5 py-3 border-b border-line last:border-0`}
            >
              {/* Rule id + badges */}
              <div className="space-y-1">
                <div className="font-mono text-xs text-slate">{r.rule_id}</div>
                <span className={SEV_BADGE[r.severity] || "badge badge-off"}>{r.severity}</span>
                <div className="badge badge-off">{r.scope}</div>
              </div>

              {/* Check name + P&P */}
              <div>
                <div className="font-medium text-ink">{r.name}</div>
                <div className="text-xs text-slate mt-0.5">P&amp;P: {cleanPP(r.pp_reference)}</div>
              </div>

              {/* Enabled */}
              <div className="flex justify-center">
                <input
                  type="checkbox"
                  className="w-4 h-4"
                  checked={val(r, "enabled") as boolean}
                  onChange={(e) => edit(r.rule_id, { enabled: e.target.checked })}
                />
              </div>

              {/* Weight */}
              <div className="flex justify-center">
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={val(r, "weight") as number}
                  onChange={(e) => edit(r.rule_id, { weight: Number(e.target.value) })}
                  className="w-20 border border-hairline rounded-lg px-2 py-1 text-sm text-center"
                />
              </div>

              {/* Explanation */}
              <div>
                <textarea
                  value={(val(r, "explanation") as string) || ""}
                  onChange={(e) => edit(r.rule_id, { explanation: e.target.value })}
                  rows={2}
                  className="w-full border border-hairline rounded-lg px-3 py-2 text-sm resize-y"
                />
              </div>

              {/* Save */}
              <div className="flex justify-end">
                <button
                  onClick={() => save(r)}
                  disabled={!dirty(r) || busy === r.rule_id}
                  className="px-3 py-1.5 rounded-lg bg-orange text-white text-sm font-medium hover:opacity-90 disabled:opacity-40"
                >
                  {busy === r.rule_id ? "…" : "Save"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
