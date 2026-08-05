import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { AgentDetail, HistoryPoint } from "../api/types";
import ScoreGauge from "../components/ScoreGauge";
import FindingsTable from "../components/FindingsTable";
import JudgeCard from "../components/JudgeCard";

function fmtDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d.toLocaleString();
}

function Meta({ label, value, mono }: { label: string; value: string | null; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate">{label}</dt>
      <dd className={`text-ink ${mono ? "font-mono text-xs break-all" : ""}`}>
        {value || <span className="text-slate">—</span>}
      </dd>
    </div>
  );
}

function HistoryChart({ data }: { data: HistoryPoint[] }) {
  if (data.length < 2)
    return <div className="text-sm text-slate">Only one scan so far — history builds up daily.</div>;
  const w = 520;
  const h = 110;
  const xs = (i: number) => (i / (data.length - 1)) * (w - 20) + 10;
  const ys = (v: number) => h - 12 - (v / 100) * (h - 24);
  const pts = data.map((d, i) => `${xs(i)},${ys(d.score ?? 0)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full">
      {[0, 40, 60, 75, 90].map((g) => (
        <line key={g} x1={10} x2={w - 10} y1={ys(g)} y2={ys(g)} stroke="var(--track)" strokeWidth="1" />
      ))}
      <polyline points={pts} fill="none" stroke="#ff5800" strokeWidth="2.5" />
      {data.map((d, i) => (
        <g key={i}>
          <circle cx={xs(i)} cy={ys(d.score ?? 0)} r="3.5" fill="#ff5800" />
          <title>
            {d.captured_at ? new Date(d.captured_at).toLocaleDateString() : ""}: {d.score}
          </title>
        </g>
      ))}
    </svg>
  );
}

export default function AgentDetailPage() {
  const { botId } = useParams();
  const [sp] = useSearchParams();
  const scanId = sp.get("scan");
  const envParam = sp.get("env");
  const backTo = envParam ? `/?env=${envParam}` : "/";
  const [detail, setDetail] = useState<AgentDetail | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    if (!botId || !scanId) return;
    const id = encodeURIComponent(botId);
    api.get<AgentDetail>(`/reports/agents/${id}?scan_id=${scanId}`).then(setDetail).catch((e) => setErr((e as Error).message));
    api.get<HistoryPoint[]>(`/reports/agents/${id}/history`).then(setHistory).catch(() => setHistory([]));
  }, [botId, scanId]);

  if (err) return <div className="text-fail">{err}</div>;
  if (!detail) return <div className="text-slate">Loading…</div>;

  const findings = detail.findings.filter((f) => {
    if (filter === "all") return true;
    if (filter === "manual") return f.manual_review;
    return f.status === filter && !f.manual_review;
  });
  const fails = detail.findings.filter((f) => f.status === "fail").length;

  return (
    <div className="space-y-6">
      <Link to={backTo} className="text-sm text-slate hover:text-ink">
        ← All agents
      </Link>

      <div className="card p-6 flex flex-col md:flex-row items-center gap-8">
        <ScoreGauge score={detail.score ?? 0} grade={detail.grade ?? "F"} />
        <div className="flex-1 w-full">
          <div className="text-2xl font-semibold text-ink">{detail.agent_name}</div>
          <div className="text-sm text-slate mt-1">
            Solution:{" "}
            {detail.solution_url ? (
              <a href={detail.solution_url} target="_blank" rel="noreferrer"
                 className="text-ink underline decoration-dotted hover:decoration-solid">
                {detail.solution_name}
              </a>
            ) : (
              detail.solution_name || <span className="text-fail">default solution (not packaged)</span>
            )}{" "}
            · {detail.publish_state} · {fails} issue(s) to address
          </div>
          <dl className="mt-4 grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3 text-sm">
            <Meta label="Environment" value={detail.environment_name} />
            <Meta label="Model" value={detail.model_hint} />
            <Meta label="Schema name" value={detail.schema_name} mono />
            <Meta label="Created" value={fmtDate(detail.created_on)} />
            <Meta label="Last modified" value={fmtDate(detail.modified_on)} />
            <Meta
              label="Created by"
              value={
                detail.created_by_name
                  ? `${detail.created_by_name}${detail.created_by_upn ? ` · ${detail.created_by_upn}` : ""}`
                  : null
              }
            />
          </dl>
          {(detail.agent_url || detail.solution_url) && (
            <div className="mt-4 flex flex-wrap gap-2">
              {detail.agent_url && (
                <a href={detail.agent_url} target="_blank" rel="noreferrer" className="btn-secondary text-sm">
                  Open agent in Copilot Studio ↗
                </a>
              )}
              {detail.solution_url && (
                <a href={detail.solution_url} target="_blank" rel="noreferrer" className="btn-secondary text-sm">
                  Open solution in maker portal ↗
                </a>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card p-5">
          <h3 className="font-semibold text-ink mb-3">Daily score history</h3>
          <HistoryChart data={history} />
        </div>
        <div className="card p-5">
          <h3 className="font-semibold text-ink mb-3">Live telemetry</h3>
          {detail.telemetry ? (
            <div className="grid grid-cols-3 gap-3 text-center">
              <div>
                <div className="text-2xl font-bold text-ink">{detail.telemetry.run_count ?? "–"}</div>
                <div className="text-xs text-slate">runs / {detail.telemetry.window_days}d</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-fail">{detail.telemetry.error_count ?? "–"}</div>
                <div className="text-xs text-slate">errors</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-ink">
                  {detail.telemetry.p95_latency_ms ? `${Math.round(detail.telemetry.p95_latency_ms)}ms` : "–"}
                </div>
                <div className="text-xs text-slate">p95 latency</div>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate">
              No Application Insights wired up for this environment.
            </div>
          )}
        </div>
      </div>

      <div className="card p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-ink">Findings &amp; explanations</h3>
          <div className="flex gap-1">
            {["all", "fail", "pass", "skipped", "manual"].map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-2.5 py-1 rounded-lg text-xs capitalize ${
                  filter === f ? "bg-strong text-white" : "bg-mist text-slate hover:text-ink"
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
        <FindingsTable findings={findings} />
      </div>

      <div className="card p-5">
        <h3 className="font-semibold text-ink mb-3">LLM judge — instruction quality</h3>
        {detail.judge ? <JudgeCard j={detail.judge} /> : <div className="text-sm text-slate">No judge result.</div>}
      </div>
    </div>
  );
}
