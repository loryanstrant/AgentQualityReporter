import { useEffect, useState } from "react";
import { api } from "../api/client";

interface About {
  version: string;
  engine_version: string;
  catalogue_hash: string;
  build_date: string;
  build_time: string;
}

export default function AboutPage() {
  const [about, setAbout] = useState<About | null>(null);

  useEffect(() => {
    api.get<About>("/reports/about").then(setAbout).catch(() => {});
  }, []);

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold text-ink">About</h1>
        <p className="mt-1 text-sm text-slate">
          What this platform does, how it scores, and who built it.
        </p>
      </div>

      <div className="card p-6">
        <h3 className="font-semibold text-ink mb-2">Copilot Studio Agent Quality Reporter</h3>
        <p className="text-sm text-slate leading-relaxed">
          A self-contained platform that reads your Copilot Studio agents live from the
          Dataverse Web API, scores each one against an editable catalogue of patterns &amp;
          practices plus an optional LLM instruction-quality judge, and presents per-agent
          scorecards, findings, and history across all of your Power Platform environments.
        </p>
        {about && (
          <p className="text-xs text-slate mt-4">
            Version <span className="font-semibold text-ink">{about.version}</span> · built{" "}
            {new Date(about.build_date).toLocaleDateString(undefined, {
              year: "numeric", month: "short", day: "numeric",
            })}
            {about.build_time ? ` at ${about.build_time}` : ""}{" "}
            · engine {about.engine_version} · rules {about.catalogue_hash}
          </p>
        )}
      </div>

      <div className="card p-6 text-sm leading-relaxed text-slate">
        <h3 className="font-semibold text-ink mb-3">How scoring works</h3>
        <ul className="list-inside list-disc space-y-1">
          <li>
            Each agent starts at <span className="font-medium text-ink">100</span> and loses the
            configured weight of every failed rule; grades are A ≥ 90, B ≥ 75, C ≥ 60, D ≥ 40,
            F below.
          </li>
          <li>
            Rules cover solution hygiene, agent configuration, and (optionally) instruction
            quality judged by an Azure OpenAI / Foundry model. Every rule is editable on the
            Rules page — enable/disable, reweight, or reword it.
          </li>
          <li>
            Application Insights (AGT-007) is manual-review: Copilot Studio stores its
            connection outside Dataverse, so a service-principal scan never fails on its absence.
          </li>
        </ul>
      </div>

      <div className="card flex items-center gap-4 p-6">
        <img
          src="/loryan-cyborg.png"
          alt="Loryan Strant"
          className="h-16 w-16 rounded-full object-cover"
        />
        <div>
          <div className="text-xs uppercase tracking-wide text-slate">Created by</div>
          <a
            href="https://www.loryanstrant.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-lg font-semibold text-orange hover:underline"
          >
            Loryan Strant
          </a>
          <div className="mt-1">
            <a
              href="https://github.com/loryanstrant/AgentQualityReporter"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-slate hover:text-orange hover:underline"
            >
              <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4 fill-current">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
              </svg>
              View on GitHub
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
