import { formatINR, toNumber } from "@/lib/format";

/** Horizontal bars for a breakdown of one quantity (one colour; values labelled at the tip). */
export function BreakdownBars({
  rows,
  format = (n) => formatINR(n),
  color = "var(--chart-1)",
}: {
  rows: { label: string; value: string | number | null | undefined }[];
  format?: (n: number) => string;
  color?: string;
}) {
  const nums = rows.map((r) => toNumber(r.value) ?? 0);
  const max = Math.max(...nums.map(Math.abs), 1);
  return (
    <table className="w-full text-xs">
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.label}>
            <td className="w-0 py-1 pr-3 whitespace-nowrap text-muted-foreground">{r.label}</td>
            <td className="py-1">
              <div className="flex items-center gap-2">
                <div
                  className="h-3 rounded-r-[4px]"
                  style={{
                    width: `${(Math.abs(nums[i]!) / max) * 100}%`,
                    minWidth: nums[i] ? 2 : 0,
                    background: color,
                    maxWidth: "calc(100% - 5rem)",
                  }}
                />
                <span className="tabular font-medium whitespace-nowrap">{format(nums[i]!)}</span>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
