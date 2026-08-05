const GRADE_COLORS: Record<string, string> = {
  A: "#2A9D8F",
  B: "#52B788",
  C: "#E9C46A",
  D: "#F4A261",
  F: "#E63946",
};

export default function ScoreGauge({
  score,
  grade,
}: {
  score: number;
  grade: string;
}) {
  const color = GRADE_COLORS[grade] || "#8D99AE";
  const r = 80;
  const cx = 100;
  const cy = 100;
  // Semicircle from 180deg -> 0deg. Fraction of the arc filled by the score.
  const frac = Math.max(0, Math.min(100, score)) / 100;
  const angle = Math.PI * (1 - frac);
  const endX = cx + r * Math.cos(angle);
  const endY = cy - r * Math.sin(angle);
  // A semicircle gauge never sweeps more than 180°, so the large-arc-flag is
  // always 0. (Setting it to 1 for high scores sends the arc the long way round,
  // producing an overflowing near-full circle.)
  const large = 0;

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 200 130" width="220">
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none"
          stroke="var(--track)"
          strokeWidth="16"
          strokeLinecap="round"
        />
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 ${large} 1 ${endX} ${endY}`}
          fill="none"
          stroke={color}
          strokeWidth="16"
          strokeLinecap="round"
        />
        <text x={cx} y={cy - 18} textAnchor="middle" fontSize="42" fontWeight="700" fill="var(--ink)">
          {score}
        </text>
        <text x={cx} y={cy + 4} textAnchor="middle" fontSize="12" fill="var(--slate)">
          / 100
        </text>
      </svg>
      <div
        className="mt-1 w-12 h-12 rounded-full grid place-items-center text-white text-xl font-bold"
        style={{ background: color }}
      >
        {grade}
      </div>
    </div>
  );
}
