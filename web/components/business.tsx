"use client";

import { Building2, Check, ChefHat, Factory, Laptop, RotateCcw, Store } from "lucide-react";
import Link from "next/link";
import { useContext, useState } from "react";
import { post } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { DataVersion } from "./data-version";
import { useToast } from "./fx";
import { cx, Sheet } from "./ui";

const TYPE_ICON: Record<string, React.ElementType> = { manufacturing: Factory, services: Laptop, restaurant: ChefHat, retail: Store };
const TYPE_GRAD: Record<string, string> = { manufacturing: "grad-sunset", services: "grad-violet", restaurant: "grad-berry", retail: "grad-mint" };

/** Switch between the demo businesses and the owner's own books. */
export function BusinessSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useT();
  const { state, refresh } = useContext(DataVersion);
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const go = async (source: string) => {
    setBusy(source);
    try {
      await post("/api/source", { source });
      refresh();
      onClose();
    } catch (e) {
      toast.show({ text: e instanceof Error ? e.message : String(e), tone: "bad" });
    } finally {
      setBusy(null);
    }
  };
  const label = (key: string) => state?.types.find((x) => x.key === key)?.label ?? key;
  return (
    <Sheet open={open} onClose={onClose} title={t("Which business?")}>
      <p className="mb-4 text-sm text-ink-2">{t("FinPilot works the same for any business. Try a demo — each has a different cash problem — or use your own books.")}</p>
      <ul className="space-y-2">
        {state?.demos.map((d) => {
          const I = TYPE_ICON[d.type] ?? Building2;
          const on = state.source === d.key;
          return (
            <li key={d.key}>
              <button onClick={() => go(d.key)} disabled={!!busy}
                className={cx("flex w-full items-start gap-3 rounded-2xl border p-3 text-left transition hover:border-brand", on ? "border-brand bg-brand-50" : "border-line bg-surface")}>
                <span className={cx("grid size-10 shrink-0 place-items-center rounded-2xl", TYPE_GRAD[d.type] ?? "grad-ocean")}>
                  <I className="size-5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 font-semibold">
                    {d.name} {on && <Check className="size-4 text-brand" />}
                  </span>
                  <span className="block text-xs text-muted">{t(label(d.type))} · {d.city} · {t("demo")}</span>
                  <span className="mt-0.5 block text-sm text-ink-2">{t(d.story)}</span>
                </span>
              </button>
            </li>
          );
        })}
        <li>
          {state?.upload.ready ? (
            <button onClick={() => go("upload")} disabled={!!busy}
              className={cx("flex w-full items-center gap-3 rounded-2xl border p-3 text-left transition hover:border-brand", state.source === "upload" ? "border-brand bg-brand-50" : "border-line bg-surface")}>
              <span className="grad-hero grid size-10 shrink-0 place-items-center rounded-2xl"><Building2 className="size-5" /></span>
              <span className="flex-1">
                <span className="block font-semibold">{state.upload.name} {state.source === "upload" && <Check className="inline size-4 text-brand" />}</span>
                <span className="block text-sm text-ink-2">{t("Your own books")}</span>
              </span>
            </button>
          ) : (
            <Link href="/data/" onClick={onClose} className="flex w-full items-center gap-3 rounded-2xl border border-dashed border-brand/50 p-3 transition hover:bg-brand-50">
              <span className="grad-hero grid size-10 shrink-0 place-items-center rounded-2xl"><Building2 className="size-5" /></span>
              <span className="flex-1">
                <span className="block font-semibold text-brand">{t("Use my own business")}</span>
                <span className="block text-sm text-ink-2">{t("Upload a bank statement (Excel/CSV), or start with just today's balance.")}</span>
              </span>
            </Link>
          )}
        </li>
      </ul>
      {state?.is_demo && (
        <button
          onClick={async () => {
            await post("/api/demo/reset", {});
            refresh();
            toast.show({ text: t("Demo reset") });
            onClose();
          }}
          className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-ink-2 hover:text-ink">
          <RotateCcw className="size-4" /> {t("Reset this demo")}
        </button>
      )}
    </Sheet>
  );
}
