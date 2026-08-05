import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { AgentListItem, EnvironmentCard, GRADE_COLORS, ScanProgress } from "../api/types";

type SortKey = "agent_name" | "solution_name" | "publish_state" | "score" | "grade" | "environment_name";

function envKey(id: number | null | undefined): string {
  return id == null ? "demo" : String(id);
}

function GradeBadge({ grade }: { grade: string | null }) {
  if (!grade) return <span className="text-slate">–</span>;
  return (
    <span
      className="inline-grid place-items-center w-7 h-7 rounded-full text-white text-sm font-bold"
      style={{ background: GRADE_COLORS[grade] || "#8D99AE" }}
    >
      {grade}
    </span>
  );
}

function ScoreBar({ score }: { score: number | null }) {
  const v = score ?? 0;
  const color = v >= 75 ? "#2A9D8F" : v >= 60 ? "#E9C46A" : v >= 40 ? "#F4A261" : "#E63946";
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-2 bg-track rounded">
        <div className="h-2 rounded" style={{ width: `${v}%`, background: color }} />
      </div>
      <span className="w-8 text-right font-semibold text-ink text-sm">{score ?? "–"}</span>
    </div>
  );
}

const ALL = "all";

export default function OverviewPage() {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const [envs, setEnvs] = useState<EnvironmentCard[]>([]);
  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [progress, setProgress] = useState<ScanProgress[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const prevRunning = useRef(0);

  // Selected environment key: "all" (default) or an env id.
  const selKey = sp.get("env") || ALL;
  const isAll = selKey === ALL;
  const selEnv = envs.find((e) => envKey(e.environment_id) === selKey) || null;

  const loadAgents = async () => {
    if (isAll) {
      setAgents(await api.get<AgentListItem[]>("/reports/all-agents"));
    } else if (selEnv) {
      setAgents(await api.get<AgentListItem[]>(`/reports/agents?scan_id=${selEnv.latest_scan_id}`));
    }
  };

  useEffect(() => {
    api.get<EnvironmentCard[]>("/reports/environments").then(setEnvs).catch((x) => setErr((x as Error).message));
  }, []);

  useEffect(() => {
    loadAgents().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selKey, envs.length]);

  // Poll for in-progress scans; refresh when the running count drops.
  useEffect(() => {
    let active = true;
    const tick = async () => {
      try {
        const p = await api.get<ScanProgress[]>("/reports/scan-progress");
        if (!active) return;
        setProgress(p);
        if (p.length < prevRunning.current) {
          setEnvs(await api.get<EnvironmentCard[]>("/reports/environments"));
          await loadAgents();
        }
        prevRunning.current = p.length;
      } catch {
        /* ignore */
      }
    };
    tick();
    const h = setInterval(tick, 2500);
    return () => {
      active = false;
      clearInterval(h);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selKey, envs.length]);

  const selectKey = (k: string) => setSp(k === ALL ? {} : { env: k }, { replace: true });

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir(key === "score" || key === "grade" ? "desc" : "asc");
    }
  };

  const sorted = useMemo(() => {
    const rows = [...agents];
    rows.sort((a, b) => {
      const av = (a as any)[sortKey];
      const bv = (b as any)[sortKey];
      let cmp: number;
      if (typeof av === "number" || typeof bv === "number") {
        cmp = (av == null ? -Infinity : av) - (bv == null ? -Infinity : bv);
      } else {
        cmp = String(av ?? "").localeCompare(String(bv ?? ""));
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return rows;
  }, [agents, sortKey, sortDir]);

  const Th = ({ label, k }: { label: string; k: SortKey }) => (
    <th
      className="py-2 pr-3 font-medium cursor-pointer select-none hover:text-ink"
      onClick={() => toggleSort(k)}
    >
      {label}
      <span className="ml-1 text-xs">{sortKey === k ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span>
    </th>
  );

  const anyScanning = progress.length > 0;
  const selProgress = selEnv ? progress.find((p) => envKey(p.environment_id) === envKey(selEnv.environment_id)) : null;
  const title = isAll ? "All environments" : selEnv?.name ?? "Agents";

  if (err) return <div className="text-fail">{err}</div>;
  if (envs.length === 0)
    return (
      <div className="card p-8 text-center text-slate">
        No scans yet. An admin can run one from the Admin page.
      </div>
    );

  return (
    <div className="space-y-6">
      {/* Environment selector. */}
      <div className="card p-4">
        <label className="block text-xs font-semibold uppercase tracking-wide text-slate mb-2">
          Environment
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={selKey}
            onChange={(ev) => selectKey(ev.target.value)}
            className="min-w-[280px] border border-hairline rounded-lg px-3 py-2 text-sm font-medium text-ink"
          >
            <option value={ALL}>All environments</option>
            {envs.map((e) => (
              <option key={envKey(e.environment_id)} value={envKey(e.environment_id)}>
                {e.name} ({e.agent_count} agents)
              </option>
            ))}
          </select>
          {isAll && anyScanning && (
            <span className="flex items-center gap-2 text-sm text-slate">
              <span className="w-2 h-2 rounded-full bg-orange animate-pulse" /> Scanning in progress…
            </span>
          )}
          {!isAll && selEnv && (
            selProgress ? (
              <span className="flex items-center gap-2 text-sm text-slate">
                <span className="w-2 h-2 rounded-full bg-orange animate-pulse" />
                Scanning {selProgress.agents_done}/{selProgress.agent_count} agent(s)…
              </span>
            ) : (
              <span className="text-sm text-slate">
                Last scanned {selEnv.scanned_at ? new Date(selEnv.scanned_at).toLocaleString() : "—"}
              </span>
            )
          )}
        </div>
      </div>

      {/* Agent table with a highlighted header bar. */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 bg-orange/10 border-b-2 border-orange">
          <h2 className="font-semibold text-ink">
            {title}
            <span className="ml-2 text-sm font-normal text-slate">
              — {isAll ? "agents across every environment" : "agents in this environment"}
            </span>
          </h2>
          <span className="text-sm font-medium text-ink">{agents.length} agent(s)</span>
        </div>
        {selProgress && (
          <div className="h-1 bg-track">
            <div
              className="h-1 bg-orange transition-all"
              style={{
                width: `${selProgress.agent_count ? (selProgress.agents_done / selProgress.agent_count) * 100 : 8}%`,
              }}
            />
          </div>
        )}
        <div className="p-5 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate border-b border-line">
                <Th label="Agent" k="agent_name" />
                {isAll && <Th label="Environment" k="environment_name" />}
                <Th label="Solution" k="solution_name" />
                <Th label="State" k="publish_state" />
                <Th label="Score" k="score" />
                <Th label="Grade" k="grade" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((a) => (
                <tr
                  key={`${a.environment_id}-${a.bot_id || a.agent_name}`}
                  className="border-b border-line hover:bg-mist/50 cursor-pointer"
                  onClick={() =>
                    a.bot_id &&
                    nav(
                      `/agents/${encodeURIComponent(a.bot_id)}?scan=${a.scan_id}&env=${envKey(a.environment_id)}`
                    )
                  }
                >
                  <td className="py-2 pr-3 font-medium text-ink">{a.agent_name}</td>
                  {isAll && <td className="py-2 pr-3 text-slate">{a.environment_name}</td>}
                  <td className="py-2 pr-3 text-slate">
                    {a.solution_name || <span className="text-fail">default solution</span>}
                  </td>
                  <td className="py-2 pr-3 text-slate capitalize">{a.publish_state || "–"}</td>
                  <td className="py-2 pr-3">
                    <ScoreBar score={a.score} />
                  </td>
                  <td className="py-2 pr-3">
                    <GradeBadge grade={a.grade} />
                  </td>
                </tr>
              ))}
              {agents.length === 0 && (
                <tr>
                  <td colSpan={isAll ? 6 : 5} className="py-6 text-center text-slate">
                    No agents.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
