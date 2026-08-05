interface Slice {
  label: string;
  value: number;
  color: string;
}

export default function Donut({ slices }: { slices: Slice[] }) {
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  const r = 60;
  const c = 2 * Math.PI * r;
  let offset = 0;

  return (
    <div className="flex items-center gap-5">
      <svg viewBox="0 0 160 160" width="150">
        <g transform="translate(80,80) rotate(-90)">
          <circle r={r} fill="none" stroke="var(--track)" strokeWidth="18" />
          {slices.map((s, i) => {
            const len = (s.value / total) * c;
            const dash = `${len} ${c - len}`;
            const el = (
              <circle
                key={i}
                r={r}
                fill="none"
                stroke={s.color}
                strokeWidth="18"
                strokeDasharray={dash}
                strokeDashoffset={-offset}
              />
            );
            offset += len;
            return el;
          })}
        </g>
        <text x="80" y="76" textAnchor="middle" fontSize="26" fontWeight="700" fill="var(--ink)">
          {total}
        </text>
        <text x="80" y="94" textAnchor="middle" fontSize="10" fill="var(--slate)">
          checks
        </text>
      </svg>
      <ul className="text-sm space-y-1">
        {slices.map((s, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-sm" style={{ background: s.color }} />
            <span className="text-slate">{s.label}</span>
            <span className="ml-auto font-semibold text-ink">{s.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
