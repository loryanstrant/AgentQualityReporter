const SEV_COLORS: Record<string, string> = {
  blocker: "#E63946",
  major: "#F4A261",
  minor: "#E9C46A",
  info: "#8AB0AB",
};

export default function SeverityBars({
  data,
}: {
  data: { blocker: number; major: number; minor: number; info: number };
}) {
  const rows = (["blocker", "major", "minor", "info"] as const).map((k) => ({
    label: k,
    value: data[k],
  }));
  const max = Math.max(1, ...rows.map((r) => r.value));

  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-3 text-sm">
          <span className="w-16 capitalize text-slate">{r.label}</span>
          <div className="flex-1 h-4 bg-track rounded">
            <div
              className="h-4 rounded"
              style={{ width: `${(r.value / max) * 100}%`, background: SEV_COLORS[r.label] }}
            />
          </div>
          <span className="w-6 text-right font-semibold text-ink">{r.value}</span>
        </div>
      ))}
    </div>
  );
}
