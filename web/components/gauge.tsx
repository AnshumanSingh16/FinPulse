"use client";

import { useCountUp } from "./fx";

/** Half-ring score gauge (0–100) with a colour sweep from coral to mint. */
export function Gauge({ score, size = 180, label }: { score: number; size?: number; label?: string }) {
  const v = useCountUp(score, 900);
  const r = 70;
  const c = Math.PI * r;
  const pct = Math.max(0, Math.min(100, v)) / 100;
  return (
    <svg viewBox="0 0 180 104" width={size} height={(size * 104) / 180} role="img" aria-label={`${label ?? "Score"} ${Math.round(score)} out of 100`}>
      <defs>
        <linearGradient id="gauge" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#ff6b6b" />
          <stop offset="50%" stopColor="#ffb547" />
          <stop offset="100%" stopColor="#22c3a6" />
        </linearGradient>
      </defs>
      <path d="M20 94 A70 70 0 0 1 160 94" fill="none" stroke="#ece9f5" strokeWidth="16" strokeLinecap="round" />
      <path d="M20 94 A70 70 0 0 1 160 94" fill="none" stroke="url(#gauge)" strokeWidth="16" strokeLinecap="round" strokeDasharray={`${c * pct} ${c}`} />
      <text x="90" y="84" textAnchor="middle" className="num" fontSize="38" fontWeight="700" fill="currentColor">
        {Math.round(v)}
      </text>
      <text x="90" y="101" textAnchor="middle" fontSize="10" fill="#8f8aa3">
        / 100
      </text>
    </svg>
  );
}

export function Ring({ pct, size = 64, stroke = 8, color = "#6a44ff" }: { pct: number; size?: number; stroke?: number; color?: string }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const p = Math.max(0, Math.min(100, pct)) / 100;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#ece9f5" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={`${c * p} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
    </svg>
  );
}
