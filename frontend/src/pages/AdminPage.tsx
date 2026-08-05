import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api/client";
import { AppConfig, Environment } from "../api/types";
import SetupWizard from "../components/SetupWizard";

function Field({
  label,
  ...props
}: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="text-sm text-slate">{label}</span>
      <input
        {...props}
        className="mt-1 w-full border border-hairline rounded-lg px-3 py-2 text-sm"
      />
    </label>
  );
}

export default function AdminPage() {
  const nav = useNavigate();
  const [cfg, setCfg] = useState<AppConfig | null>(null);
  const [envs, setEnvs] = useState<Environment[]>([]);
  const [about, setAbout] = useState<{ version: string; engine_version: string; catalogue_hash: string; build_date: string; build_time: string } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // config form state
  const [form, setForm] = useState<Record<string, string>>({});
  // new environment form
  const [env, setEnv] = useState<Record<string, string>>({});
  // inline edit of an existing environment
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<Record<string, string>>({});

  const load = async () => {
    setCfg(await api.get<AppConfig>("/admin/config"));
    setEnvs(await api.get<Environment[]>("/admin/environments"));
    api.get<typeof about>("/admin/about").then(setAbout).catch(() => {});
  };
  useEffect(() => {
    load().catch((e) => setMsg((e as Error).message));
  }, []);

  const flash = (m: string) => {
    setMsg(m);
    setTimeout(() => setMsg(null), 4000);
  };

  const saveConfig = async () => {
    setBusy(true);
    try {
      const body: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(form)) if (v !== "") body[k] = v;
      if (form.schedule_interval_hours) body.schedule_interval_hours = Number(form.schedule_interval_hours);
      await api.put("/admin/config", body);
      setForm({});
      await load();
      flash("Configuration saved.");
    } catch (e) {
      flash((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const scanEnv = async (id: number) => {
    setBusy(true);
    try {
      const r = await api.post<{ status: string; detail: string }>(
        `/admin/scan/run?source=dataverse&environment_id=${id}`
      );
      if (r.status === "already_running") {
        flash(r.detail);
      } else {
        flash("Scan started — watch progress on the Overview page.");
        nav(`/?env=${id}`);
      }
    } catch (e) {
      flash((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const scanAll = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ status: string; detail: string }>("/admin/scan/all");
      if (r.status === "already_running") flash(r.detail);
      else {
        flash(r.detail);
        nav("/");
      }
    } catch (e) {
      flash((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const testConn = async (id: number) => {
    setBusy(true);
    try {
      const r = await api.post<{ ok: boolean; detail: string }>(
        `/admin/test-connection?environment_id=${id}`
      );
      flash(r.detail);
    } catch (e) {
      flash((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const addEnv = async () => {
    setBusy(true);
    try {
      await api.post("/admin/environments", {
        display_name: env.display_name,
        dataverse_url: env.dataverse_url,
        app_insights_app_id: env.app_insights_app_id,
        app_insights_key: env.app_insights_key,
        enabled: true,
      });
      setEnv({});
      await load();
      flash("Environment added.");
    } catch (e) {
      flash((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const delEnv = async (id: number) => {
    await api.del(`/admin/environments/${id}`);
    await load();
  };

  const startEdit = (e: Environment) => {
    setEditingId(e.id);
    setEditForm({
      display_name: e.display_name,
      dataverse_url: e.dataverse_url || "",
      app_insights_app_id: e.app_insights_app_id || "",
      app_insights_key: "",
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm({});
  };

  const saveEdit = async (e: Environment) => {
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        display_name: editForm.display_name,
        dataverse_url: editForm.dataverse_url,
        app_insights_app_id: editForm.app_insights_app_id,
        enabled: e.enabled,
      };
      // Only send the key when the admin typed a new one (blank keeps existing).
      if (editForm.app_insights_key) body.app_insights_key = editForm.app_insights_key;
      await api.put(`/admin/environments/${e.id}`, body);
      cancelEdit();
      await load();
      flash("Environment updated.");
    } catch (err) {
      flash((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!cfg) return <div className="text-slate">Loading…</div>;

  return (
    <div className="space-y-6">
      {msg && <div className="card p-3 text-sm text-ink border-l-4 border-orange">{msg}</div>}

      <div className="card p-5">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-ink">Status</h3>
            <p className="text-sm text-slate mt-1">
              Service principal {cfg.configured ? "✓ configured" : "✗ not configured"} · LLM judge{" "}
              {cfg.judge_configured ? "✓ configured" : "✗ not configured"}
            </p>
            {about && (
              <p className="text-xs text-slate mt-2">
                Version <span className="font-semibold text-ink">{about.version}</span> · built{" "}
                {new Date(about.build_date).toLocaleDateString(undefined, {
                  year: "numeric", month: "short", day: "numeric",
                })}
                {about.build_time ? ` at ${about.build_time}` : ""}{" "}
                · engine {about.engine_version} · rules {about.catalogue_hash}
              </p>
            )}
          </div>
          <Link
            to="/rules"
            className="px-4 py-2 rounded-lg border border-hairline hover:bg-mist text-ink text-sm font-medium"
          >
            Manage rules →
          </Link>
        </div>
      </div>

      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-ink">Environments</h3>
          <button
            onClick={scanAll}
            disabled={busy || envs.length === 0}
            className="px-4 py-2 rounded-lg bg-orange text-white text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            Scan all environments
          </button>
        </div>
        <div className="space-y-2 mb-4">
          {envs.map((e) =>
            editingId === e.id ? (
              <div key={e.id} className="border border-orange rounded-lg p-3 space-y-3">
                <div className="text-xs font-semibold text-slate uppercase tracking-wide">
                  Editing environment
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <Field label="Display name" value={editForm.display_name || ""} onChange={(ev) => setEditForm({ ...editForm, display_name: ev.target.value })} />
                  <Field label="Dataverse URL" placeholder="https://org.crm.dynamics.com" value={editForm.dataverse_url || ""} onChange={(ev) => setEditForm({ ...editForm, dataverse_url: ev.target.value })} />
                  <Field label="App Insights App ID (optional)" value={editForm.app_insights_app_id || ""} onChange={(ev) => setEditForm({ ...editForm, app_insights_app_id: ev.target.value })} />
                  <Field
                    label={`App Insights API key ${e.has_app_insights_key ? "(set — leave blank to keep)" : "(optional)"}`}
                    type="password"
                    placeholder={e.has_app_insights_key ? "••••••" : ""}
                    value={editForm.app_insights_key || ""}
                    onChange={(ev) => setEditForm({ ...editForm, app_insights_key: ev.target.value })}
                  />
                </div>
                <div className="flex gap-2">
                  <button onClick={() => saveEdit(e)} disabled={busy || !editForm.display_name} className="text-sm px-3 py-1.5 rounded-lg bg-orange text-white hover:opacity-90 disabled:opacity-50">
                    Save changes
                  </button>
                  <button onClick={cancelEdit} disabled={busy} className="text-sm px-3 py-1.5 rounded-lg border border-hairline hover:bg-mist">
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div key={e.id} className="flex items-center gap-3 border border-line rounded-lg p-3">
                <div className="flex-1">
                  <div className="font-medium text-ink">{e.display_name}</div>
                  <div className="text-xs text-slate">{e.dataverse_url || "no Dataverse URL"}</div>
                  <div className="text-xs text-slate mt-0.5">
                    {e.app_insights_app_id || e.has_app_insights_key
                      ? "App Insights connected"
                      : "No App Insights"}
                    {" · "}
                    {e.last_scanned
                      ? `Last scanned ${new Date(e.last_scanned).toLocaleString()}${
                          e.last_agent_count != null ? ` · ${e.last_agent_count} agents` : ""
                        }`
                      : "Never scanned"}
                  </div>
                </div>
                <button onClick={() => startEdit(e)} disabled={busy} className="text-sm px-3 py-1.5 rounded-lg border border-hairline hover:bg-mist">
                  Edit
                </button>
                <button onClick={() => testConn(e.id)} disabled={busy} className="text-sm px-3 py-1.5 rounded-lg border border-hairline hover:bg-mist">
                  Test
                </button>
                <button onClick={() => scanEnv(e.id)} disabled={busy} className="text-sm px-3 py-1.5 rounded-lg bg-strong text-white hover:opacity-90">
                  Scan now
                </button>
                <button onClick={() => delEnv(e.id)} className="text-sm px-3 py-1.5 rounded-lg text-fail hover:bg-fail/10">
                  Delete
                </button>
              </div>
            )
          )}
          {envs.length === 0 && <div className="text-sm text-slate">No environments yet.</div>}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border-t border-line pt-4">
          <div className="md:col-span-2 text-xs font-semibold text-slate uppercase tracking-wide">
            Add a new environment
          </div>
          <Field label="Display name" value={env.display_name || ""} onChange={(e) => setEnv({ ...env, display_name: e.target.value })} />
          <Field label="Dataverse URL" placeholder="https://org.crm.dynamics.com" value={env.dataverse_url || ""} onChange={(e) => setEnv({ ...env, dataverse_url: e.target.value })} />
          <Field label="App Insights App ID (optional)" value={env.app_insights_app_id || ""} onChange={(e) => setEnv({ ...env, app_insights_app_id: e.target.value })} />
          <Field label="App Insights API key (optional)" type="password" value={env.app_insights_key || ""} onChange={(e) => setEnv({ ...env, app_insights_key: e.target.value })} />
          <div className="md:col-span-2">
            <button onClick={addEnv} disabled={busy || !env.display_name} className="px-4 py-2 rounded-lg bg-strong text-white text-sm hover:opacity-90 disabled:opacity-50">
              Add environment
            </button>
          </div>
        </div>
      </div>

      <div className="card p-5">
        <h3 className="font-semibold text-ink mb-1">Service principal &amp; judge</h3>
        <p className="text-sm text-slate mb-4">
          Secrets are write-only and stored encrypted. Leave a secret blank to keep the existing value.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Tenant ID" defaultValue={cfg.tenant_id || ""} onChange={(e) => setForm({ ...form, tenant_id: e.target.value })} />
          <Field label="Client ID" defaultValue={cfg.client_id || ""} onChange={(e) => setForm({ ...form, client_id: e.target.value })} />
          <Field label={`Client secret ${cfg.has_client_secret ? "(set)" : ""}`} type="password" placeholder="••••••" onChange={(e) => setForm({ ...form, client_secret: e.target.value })} />
          <Field label="Report access group ID (optional)" defaultValue={cfg.report_access_group_id || ""} onChange={(e) => setForm({ ...form, report_access_group_id: e.target.value })} />
          <Field label="Foundry base URL" placeholder="https://x.openai.azure.com/openai/v1/" defaultValue={cfg.aoai_base_url || ""} onChange={(e) => setForm({ ...form, aoai_base_url: e.target.value })} />
          <Field label="Foundry model" placeholder="gpt-4.1" defaultValue={cfg.aoai_model || ""} onChange={(e) => setForm({ ...form, aoai_model: e.target.value })} />
          <Field label={`Foundry API key ${cfg.has_aoai_key ? "(set)" : ""}`} type="password" placeholder="••••••" onChange={(e) => setForm({ ...form, aoai_key: e.target.value })} />
          <Field label="Scan every N hours (1–24)" type="number" min={1} max={24} defaultValue={String(cfg.schedule_interval_hours)} onChange={(e) => setForm({ ...form, schedule_interval_hours: e.target.value })} />
        </div>
        <button onClick={saveConfig} disabled={busy} className="mt-4 px-4 py-2 rounded-lg bg-orange text-white text-sm font-medium hover:opacity-90 disabled:opacity-50">
          Save configuration
        </button>
      </div>

      <SetupWizard defaultOpen={!cfg.configured} />
    </div>
  );
}
