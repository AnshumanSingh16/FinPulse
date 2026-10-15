"use client";

import {
  Banknote, Briefcase, Building2, Coffee, Cpu, Fuel, HandCoins, Landmark, Lightbulb, Megaphone, Package, PiggyBank, Receipt, ShieldCheck,
  ShoppingBasket, Store, Tag, Truck, Users, Wallet, Wrench, Wifi,
} from "lucide-react";
import { cx } from "./ui";

const MAP: [RegExp, React.ElementType, string, string][] = [
  [/sales|income|service/i, Store, "#e5f7ef", "#0e9f6e"],
  [/raw|purchase|stock|material/i, ShoppingBasket, "#fff1dc", "#c26a00"],
  [/salar|wage|staff pay/i, Users, "#efe9ff", "#6a44ff"],
  [/rent/i, Building2, "#e6f2fd", "#2a78d6"],
  [/electric|power/i, Lightbulb, "#fff8d6", "#b58100"],
  [/logist|freight|courier|transport/i, Truck, "#e3f8f6", "#0b8f86"],
  [/packag/i, Package, "#ffece3", "#d4561f"],
  [/market|advert/i, Megaphone, "#fde8f3", "#c2287a"],
  [/software|subscription/i, Cpu, "#eaecff", "#4a50d8"],
  [/bank charge|charges/i, Landmark, "#eef0f4", "#5b6577"],
  [/professional|consult|ca /i, Briefcase, "#e3f6fb", "#0e7fa3"],
  [/gst|tds|tax/i, Receipt, "#fdecec", "#c2332f"],
  [/loan|emi/i, HandCoins, "#f3e8ff", "#8b3fd8"],
  [/drawing|owner/i, Wallet, "#f1f1f1", "#555068"],
  [/insurance/i, ShieldCheck, "#e7f6ec", "#2f8f4a"],
  [/repair|mainten/i, Wrench, "#eef0f4", "#5b6577"],
  [/travel|fuel|petrol/i, Fuel, "#e9f2fd", "#2a78d6"],
  [/utilit|phone|internet/i, Wifi, "#e6f2fd", "#2a78d6"],
  [/welfare|food|tea|chai/i, Coffee, "#fff1dc", "#a85d00"],
  [/machine|equipment/i, Cpu, "#efe9ff", "#6a44ff"],
  [/transfer|cash withdraw/i, Banknote, "#eef0f4", "#5b6577"],
  [/interest|refund/i, PiggyBank, "#e5f7ef", "#0e9f6e"],
];

export function catStyle(category: string) {
  for (const [re, I, bg, fg] of MAP) if (re.test(category)) return { I, bg, fg };
  return { I: Tag, bg: "#f0eef6", fg: "#6b6680" };
}

export function CatIcon({ category, size = "md", className }: { category: string; size?: "sm" | "md" | "lg"; className?: string }) {
  const { I, fg } = catStyle(category);
  const box = size === "sm" ? "size-8" : size === "lg" ? "size-12" : "size-10";
  const ic = size === "sm" ? "size-4" : size === "lg" ? "size-6" : "size-5";
  return (
    <span className={cx("grid shrink-0 place-items-center rounded-2xl border", box, className)} style={{ background: `${fg}1f`, borderColor: `${fg}40`, color: `color-mix(in srgb, ${fg} 55%, white)` }} aria-hidden>
      <I className={ic} />
    </span>
  );
}

const AVATAR = ["#6a44ff", "#ff7a59", "#0e9f6e", "#2a78d6", "#c2287a", "#c26a00", "#0b8f86", "#8b3fd8"];

export function Avatar({ name, size = "md" }: { name: string; size?: "md" | "lg" }) {
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("") || "?";
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const c = AVATAR[h % AVATAR.length];
  return (
    <span className={cx("grid shrink-0 place-items-center rounded-full font-semibold text-white", size === "lg" ? "size-14 text-lg" : "size-11 text-sm")} style={{ background: c }} aria-hidden>
      {initials}
    </span>
  );
}
