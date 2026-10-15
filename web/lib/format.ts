/** ₹ with Indian digit grouping: 1485414 → ₹14,85,414. */
export function inr(x: number | null | undefined): string {
  if (x == null || Number.isNaN(x)) return "—";
  const neg = x < 0;
  const s = Math.round(Math.abs(x)).toString();
  let out = s;
  if (s.length > 3) {
    let head = s.slice(0, -3);
    const tail = s.slice(-3);
    const parts: string[] = [];
    while (head.length > 2) {
      parts.unshift(head.slice(-2));
      head = head.slice(0, -2);
    }
    if (head) parts.unshift(head);
    out = parts.join(",") + "," + tail;
  }
  return `${neg ? "−" : ""}₹${out}`;
}

function trim(n: number): string {
  return n.toFixed(2).replace(/\.?0+$/, "");
}

/** Compact: ₹14.85 L, ₹1.2 Cr, ₹45,000. */
export function short(x: number | null | undefined): string {
  if (x == null || Number.isNaN(x)) return "—";
  const a = Math.abs(x);
  const sign = x < 0 ? "−" : "";
  if (a >= 1e7) return `${sign}₹${trim(a / 1e7)} Cr`;
  if (a >= 1e5) return `${sign}₹${trim(a / 1e5)} L`;
  return inr(x);
}

/** Axis ticks: ₹15L, ₹500K. */
export function tick(x: number): string {
  const a = Math.abs(x);
  const sign = x < 0 ? "−" : "";
  if (a >= 1e7) return `${sign}₹${+(a / 1e7).toFixed(1)}Cr`;
  if (a >= 1e5) return `${sign}₹${+(a / 1e5).toFixed(1)}L`;
  if (a >= 1e3) return `${sign}₹${Math.round(a / 1e3)}K`;
  return `${sign}₹${a}`;
}

export function day(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function dayFull(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

/** Words for an amount typed by the owner: 1200000 → "₹12 lakh". */
export function words(x: number): string {
  if (!x) return "";
  if (x >= 1e7) return `${trim(x / 1e7)} crore`;
  if (x >= 1e5) return `${trim(x / 1e5)} lakh`;
  if (x >= 1e3) return `${trim(x / 1e3)} thousand`;
  return "";
}

export function pct(x: number | null | undefined): string {
  if (x == null) return "";
  return `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(0)}%`;
}
