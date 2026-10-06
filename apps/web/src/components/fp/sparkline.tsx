/** A small trend line (decorative; the values are always shown elsewhere on the page). */
export function Sparkline({
  values,
  width = 120,
  height = 36,
  color = "var(--chart-1)",
  domain,
}: {
  values: (number | null)[];
  width?: number;
  height?: number;
  color?: string;
  domain?: [number, number];
}) {
  const nums = values.filter((v): v is number => v !== null);
  if (nums.length < 2) return null;
  const [lo, hi] = domain ?? [Math.min(...nums), Math.max(...nums)];
  const span = hi - lo || 1;
  const pad = 4;
  const x = (i: number) => pad + (i * (width - 2 * pad)) / (values.length - 1);
  const y = (v: number) => pad + (1 - (v - lo) / span) * (height - 2 * pad);
  let d = "";
  values.forEach((v, i) => {
    if (v === null) return;
    d += `${d && values[i - 1] !== null ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
  });
  const lastIndex = values.length - 1 - [...values].reverse().findIndex((v) => v !== null);
  const last = values[lastIndex] as number;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle
        cx={x(lastIndex)}
        cy={y(last)}
        r={4}
        fill={color}
        stroke="var(--card)"
        strokeWidth={2}
      />
    </svg>
  );
}
