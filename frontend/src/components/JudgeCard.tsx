import { Judge } from "../api/types";

function Bar({ label, value, max = 5 }: { label: string; value: number | null; max?: number }) {
  const v = value ?? 0;
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-28 text-slate">{label}</span>
      <div className="flex-1 h-3 bg-track rounded">
        <div className="h-3 rounded bg-orange" style={{ width: `${(v / max) * 100}%` }} />
      </div>
      <span className="w-10 text-right font-semibold text-ink">
        {value == null ? "–" : `${v}/${max}`}
      </span>
    </div>
  );
}

function Flag({ label, on }: { label: string; on: boolean | null }) {
  return (
    <span className={`badge ${on ? "badge-pass" : "badge-off"}`}>
      {on ? "✓" : "–"} {label}
    </span>
  );
}

export default function JudgeCard({ j }: { j: Judge }) {
  if (j.skipped || j.error) {
    return (
      <div className="text-sm text-slate">
        {j.error ? `Judge error: ${j.error}` : j.summary || "LLM judge not run for this scan."}
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Bar label="Clarity" value={j.clarity} />
        <Bar label="Scope discipline" value={j.scope_discipline} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Flag label="Persona" on={j.persona_defined} />
        <Flag label="Orchestrator" on={j.orchestrator_pattern_detected} />
        <Flag label="Child pattern" on={j.child_pattern_detected} />
        <Flag label="Output format" on={j.output_format_guidance} />
      </div>
      {j.summary && <p className="text-sm text-slate">{j.summary}</p>}
      {(j.recommended_changes || j.top_weaknesses) && (
        <div>
          <div className="text-xs font-semibold text-slate uppercase tracking-wide mb-1">
            Recommended changes
          </div>
          <ul className="list-disc pl-5 text-sm text-ink space-y-0.5">
            {(j.recommended_changes || j.top_weaknesses || []).map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
