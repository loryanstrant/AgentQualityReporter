export default function Kpi({
  label,
  value,
  tone = "ink",
}: {
  label: string;
  value: string | number;
  tone?: "ink" | "pass" | "fail" | "skip" | "manual";
}) {
  const colors: Record<string, string> = {
    ink: "#333333",
    pass: "#2A9D8F",
    fail: "#E63946",
    skip: "#8D99AE",
    manual: "#6C63FF",
  };
  return (
    <div className="card p-4">
      <div className="text-3xl font-bold" style={{ color: colors[tone] }}>
        {value}
      </div>
      <div className="text-sm text-slate mt-1">{label}</div>
    </div>
  );
}
