"use client";

import { useCallback, useContext, useEffect, useState } from "react";
import { ArrowUpRight, Boxes, BriefcaseBusiness, CircleAlert, CircleCheck, Lightbulb, MessageSquareText, Upload } from "lucide-react";
import { DataVersion } from "@/components/data-version";
import { Button, cx } from "@/components/ui";
import { get, post, postForm } from "@/lib/api";
import { inr } from "@/lib/format";
import { useT } from "@/lib/i18n";

type Product = { id: number; name: string; sku: string; stock_qty: number; unit_cost: number; selling_price: number; monthly_units_sold: number; lead_time_days: number };
type Service = { id: number; name: string; price: number; delivery_cost: number; monthly_capacity: number; monthly_bookings: number };
type Opportunity = { key: string; kind: string; tone: string; title: string; reason: string; impact: number | null; basis: string; status: string; outcome_note: string };
type FeedbackRecord = { id: number; customer: string; text: string; date: string; source: string; sentiment: "positive" | "neutral" | "negative" | "uncertain"; score: number; matched_features: string[] };
type FeedbackAnalysis = { model: string; training: string; limitation: string; counts: Record<string, number>; total: number; records: FeedbackRecord[] };
type Intelligence = { profile: { name: string; category: string; type: string; model: string; information: string }; inventory: Product[]; services: Service[]; opportunities: Opportunity[]; feedback: FeedbackAnalysis };
type Scenario = Record<string, any>;

const blankProduct = { name: "", sku: "", stock_qty: "", unit_cost: "", selling_price: "", monthly_units_sold: "", lead_time_days: "" };
const blankService = { name: "", price: "", delivery_cost: "", monthly_capacity: "", monthly_bookings: "" };

export default function IntelligencePage() {
  const { t } = useT();
  const { state, refresh } = useContext(DataVersion);
  const [data, setData] = useState<Intelligence | null>(null);
  const [product, setProduct] = useState(blankProduct);
  const [service, setService] = useState(blankService);
  const [feedbackText, setFeedbackText] = useState("");
  const [feedbackCustomer, setFeedbackCustomer] = useState("");
  const [profile, setProfile] = useState({ name: "", category: "hybrid", type: "", model: "", information: "" });
  const [scenarioKind, setScenarioKind] = useState("inventory_discount");
  const [scenarioName, setScenarioName] = useState("");
  const [change, setChange] = useState("10");
  const [uplift, setUplift] = useState("");
  const [quantity, setQuantity] = useState("10");
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => get<Intelligence>("/api/intelligence").then((x) => { setData(x); setProfile(x.profile); }).catch((e) => setError(String(e))), []);
  useEffect(() => { load(); }, [load, state?.source]);
  const saveProfile = async () => { setBusy(true); setError(""); try { await post("/api/business-profile", profile); await load(); refresh(); } catch (e) { setError(String(e)); } finally { setBusy(false); } };
  const saveRecord = async (kind: "inventory" | "services") => { setBusy(true); setError(""); try { await post(`/api/intelligence/${kind}`, kind === "inventory" ? product : service); if (kind === "inventory") setProduct(blankProduct); else setService(blankService); await load(); refresh(); } catch (e) { setError(String(e)); } finally { setBusy(false); } };
  const importFile = async (kind: "inventory" | "services" | "feedback", file?: File) => { if (!file) return; const form = new FormData(); form.set("kind", kind); form.set("file", file); setBusy(true); setError(""); try { await postForm("/api/intelligence/import", form); await load(); refresh(); } catch (e) { setError(String(e)); } finally { setBusy(false); } };
  const addFeedback = async () => { setBusy(true); setError(""); try { await post("/api/intelligence/feedback", { customer: feedbackCustomer, text: feedbackText }); setFeedbackCustomer(""); setFeedbackText(""); await load(); } catch (e) { setError(String(e)); } finally { setBusy(false); } };
  const simulate = async () => { setBusy(true); setError(""); try { const result = await post<Scenario>("/api/intelligence/simulate", { kind: scenarioKind, name: scenarioName, change_pct: Number(change), volume_uplift_pct: Number(uplift || 0), quantity: Number(quantity) }); setScenario(result); } catch (e) { setError(String(e)); setScenario(null); } finally { setBusy(false); } };
  const outcome = async (item: Opportunity, status: string) => { try { await post("/api/intelligence/opportunity", { key: item.key, status, note: (document.querySelector(`[data-outcome="${CSS.escape(item.key)}"]`) as HTMLInputElement | null)?.value ?? "" }); await load(); } catch (e) { setError(String(e)); } };
  const modes = profile.category === "hybrid" ? ["inventory", "service"] : [profile.category];
  const isRestock = scenarioKind === "restock";
  const isInventoryScenario = scenarioKind.startsWith("inventory_") || isRestock;
  return <div className="intelligence-page space-y-6 pb-12">
    <header className="flex items-start gap-3"><span className="grid size-12 place-items-center rounded-2xl bg-brand-50 text-brand"><Lightbulb className="size-6" /></span><div><h1 className="text-3xl">{t("Business Opportunity Intelligence")}</h1><p className="mt-1 max-w-2xl text-sm text-ink-2">{t("One view of the business, backed by your financial books and the operational records you enter here. Scenarios show their assumptions.")}</p></div></header>
    {state?.is_demo && <div className="flex items-start gap-3 rounded-2xl border border-info/20 bg-info-50 p-4 text-sm"><CircleCheck className="mt-0.5 size-5 shrink-0 text-info" /><p><b>{t("Demo walkthrough data")}</b><br />{t("This business is preloaded with fictional product, service and customer feedback records so you can explore its tailored analysis. Demo figures and comments are illustrative.")}</p></div>}
    {error && <div className="rounded-xl bg-bad-50 p-3 text-sm text-bad">{error}</div>}

    <section className="card space-y-4"><div><h2 className="text-lg font-semibold">{t("Business profile")}</h2><p className="text-sm text-ink-2">{t("Choose which intelligence applies to this business.")}</p></div><div className="grid gap-3 sm:grid-cols-2">
      <Field label={t("Business name")} value={profile.name} onChange={(v) => setProfile({ ...profile, name: v })} />
      <label className="block text-sm"><span className="mb-1 block text-ink-2">{t("Business model")}</span><select value={profile.category} onChange={(e) => setProfile({ ...profile, category: e.target.value })} className="h-10 w-full rounded-xl border border-line bg-surface px-3"><option value="inventory">{t("Inventory based")}</option><option value="service">{t("Service based")}</option><option value="hybrid">{t("Hybrid")}</option></select></label>
      <Field label={t("Business type (e.g. boutique, studio, freelancer)")} value={profile.type} onChange={(v) => setProfile({ ...profile, type: v })} />
      <Field label={t("Business model details")} value={profile.model} onChange={(v) => setProfile({ ...profile, model: v })} />
      <label className="block text-sm sm:col-span-2"><span className="mb-1 block text-ink-2">{t("Relevant business information")}</span><textarea value={profile.information} onChange={(e) => setProfile({ ...profile, information: e.target.value })} maxLength={1000} rows={2} className="w-full rounded-xl border border-line bg-surface px-3 py-2" /></label>
    </div><Button onClick={saveProfile} disabled={busy}>{t("Save business profile")}</Button></section>

    <section className="card space-y-4"><header className="flex items-start gap-3"><MessageSquareText className="mt-1 size-5 text-brand" /><div><h2 className="text-lg font-semibold">{t("Customer Feedback Sentiment")}</h2><p className="text-sm text-ink-2">{t("See the overall tone of customer comments at a glance.")}</p></div></header>
      <div className="rounded-xl bg-surface-2 p-4 text-sm leading-relaxed text-ink-2">{t("Sentiment labels are a helpful guide. Read each comment in context before deciding what action to take.")}</div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{(["positive", "neutral", "negative", "uncertain"] as const).map((label) => <div key={label} className="rounded-xl border border-line p-3"><div className="text-xs capitalize text-muted">{t(label)}</div><div className="mt-1 text-xl font-semibold">{data?.feedback.counts[label] ?? 0}</div></div>)}</div>
      <div className="grid gap-3 sm:grid-cols-[1fr_2fr]"><Field label={t("Customer (optional)")} value={feedbackCustomer} onChange={setFeedbackCustomer} /><label className="block text-sm"><span className="mb-1 block text-ink-2">{t("Customer comment")}</span><textarea value={feedbackText} maxLength={1000} rows={2} onChange={(e) => setFeedbackText(e.target.value)} className="w-full rounded-xl border border-line bg-surface px-3 py-2" /></label></div>
      <div className="flex flex-wrap gap-2"><Button onClick={addFeedback} disabled={busy || !feedbackText.trim()}>{t("Analyse feedback")}</Button><ImportButton label={t("Import feedback CSV / Excel")} onFile={(f) => importFile("feedback", f)} /></div>
      {data?.feedback.records.length ? <div className="space-y-2">{data.feedback.records.map((f) => <article key={f.id} className="rounded-xl border border-line p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-semibold">{f.customer || t("Customer")}</span><span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${f.sentiment === "positive" ? "bg-good-50 text-good" : f.sentiment === "negative" ? "bg-bad-50 text-bad" : f.sentiment === "uncertain" ? "bg-caution-50 text-caution" : "bg-info-50 text-info"}`}>{t(f.sentiment)} · {t("model score")} {f.score.toFixed(2)}</span></div><p className="mt-2 text-sm text-ink-2">{f.text}</p><div className="mt-2 flex flex-wrap items-center gap-1.5 text-[0.68rem] text-muted"><span>{f.source}</span>{f.matched_features.map((x) => <span key={x} className="rounded bg-surface-2 px-1.5 py-0.5">{x.replaceAll("_", " ")}</span>)}</div></article>)}</div> : <Empty>{t("No customer feedback yet. Add comments or import a CSV with a text, feedback, comment or review column.")}</Empty>}
    </section>

    {modes.includes("inventory") && <section className="card space-y-4"><header className="flex items-center gap-2"><Boxes className="size-5 text-brand" /><div><h2 className="text-lg font-semibold">{t("Inventory & Sales Intelligence")}</h2><p className="text-sm text-ink-2">{t("Enter products, recorded stock, costs, selling price and monthly sales quantity.")}</p></div></header>
      <div className="grid gap-3 sm:grid-cols-3">{Object.entries({ name: t("Product name"), sku: "SKU", stock_qty: t("Stock quantity"), unit_cost: t("Unit cost (₹)"), selling_price: t("Selling price (₹)"), monthly_units_sold: t("Units sold per month"), lead_time_days: t("Restock lead time (days)") }).map(([key, label]) => <Field key={key} label={label} value={(product as any)[key]} type={key === "name" || key === "sku" ? "text" : "number"} onChange={(v) => setProduct({ ...product, [key]: v })} />)}</div>
      <div className="flex flex-wrap gap-2"><Button onClick={() => saveRecord("inventory")} disabled={busy}>{t("Save product")}</Button><ImportButton label={t("Import products CSV / Excel")} onFile={(f) => importFile("inventory", f)} /></div>
      {data?.inventory.length ? <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-muted"><tr><th className="py-2">{t("Product")}</th><th>{t("Stock")}</th><th>{t("Cost")}</th><th>{t("Price")}</th><th>{t("Units/month")}</th></tr></thead><tbody>{data.inventory.map((p) => <tr key={p.id} className="border-t border-line"><td className="py-2 font-medium">{p.name}</td><td>{p.stock_qty}</td><td>{inr(p.unit_cost)}</td><td>{inr(p.selling_price)}</td><td>{p.monthly_units_sold}</td></tr>)}</tbody></table></div> : <Empty>{t("No product records yet. Enter them or import a file to activate inventory analysis.")}</Empty>}
    </section>}

    {modes.includes("service") && <section className="card space-y-4"><header className="flex items-center gap-2"><BriefcaseBusiness className="size-5 text-brand" /><div><h2 className="text-lg font-semibold">{t("Service & Growth Intelligence")}</h2><p className="text-sm text-ink-2">{t("Enter prices, delivery costs, monthly bookings and capacity for each service.")}</p></div></header>
      <div className="grid gap-3 sm:grid-cols-3">{Object.entries({ name: t("Service / package name"), price: t("Price per booking (₹)"), delivery_cost: t("Delivery cost per booking (₹)"), monthly_capacity: t("Monthly capacity (bookings)"), monthly_bookings: t("Bookings per month") }).map(([key, label]) => <Field key={key} label={label} value={(service as any)[key]} type={key === "name" ? "text" : "number"} onChange={(v) => setService({ ...service, [key]: v })} />)}</div>
      <div className="flex flex-wrap gap-2"><Button onClick={() => saveRecord("services")} disabled={busy}>{t("Save service")}</Button><ImportButton label={t("Import services CSV / Excel")} onFile={(f) => importFile("services", f)} /></div>
      {data?.services.length ? <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-muted"><tr><th className="py-2">{t("Service")}</th><th>{t("Price")}</th><th>{t("Delivery cost")}</th><th>{t("Bookings")}</th><th>{t("Capacity")}</th></tr></thead><tbody>{data.services.map((s) => <tr key={s.id} className="border-t border-line"><td className="py-2 font-medium">{s.name}</td><td>{inr(s.price)}</td><td>{inr(s.delivery_cost)}</td><td>{s.monthly_bookings}</td><td>{s.monthly_capacity || "—"}</td></tr>)}</tbody></table></div> : <Empty>{t("No service records yet. Enter them or import a file to activate service analysis.")}</Empty>}
    </section>}

    <section className="card space-y-4"><header><h2 className="text-lg font-semibold">{t("Opportunities from your records")}</h2><p className="text-sm text-ink-2">{t("Calculated signals from the operational values entered above. These are prompts to review, not forecasts.")}</p></header>
      {data?.opportunities.length ? <div className="space-y-3">{data.opportunities.map((o) => <article key={o.key} className="rounded-2xl border border-line p-4"><div className="flex items-start gap-3"><CircleAlert className={cx("mt-0.5 size-5 shrink-0", o.tone === "caution" ? "text-caution" : "text-info")} /><div className="min-w-0 flex-1"><h3 className="font-semibold">{o.title}</h3><p className="mt-1 text-sm text-ink-2">{o.reason}</p>{o.impact !== null && <p className="mt-2 text-sm">{t("Amount to review")}: <b>{inr(o.impact)}</b></p>}<p className="mt-2 text-xs text-muted">{o.basis}</p>{o.status === "implemented" && o.outcome_note && <p className="mt-2 rounded-lg bg-good-50 p-2 text-sm">{t("Outcome recorded")}: {o.outcome_note}</p>}{o.status !== "dismissed" && <div className="mt-3 flex flex-wrap items-center gap-2"><input data-outcome={o.key} defaultValue={o.outcome_note} placeholder={t("Actual result (optional)")} className="h-9 min-w-48 flex-1 rounded-full border border-line bg-surface px-3 text-sm" /><Button variant="secondary" onClick={() => outcome(o, "implemented")}><CircleCheck className="size-4" />{o.status === "implemented" ? t("Update outcome") : t("I implemented this")}</Button>{o.status === "implemented" && <button onClick={() => outcome(o, "open")} className="px-3 text-sm text-muted">{t("Reopen")}</button>}<button onClick={() => outcome(o, "dismissed")} className="px-3 text-sm text-muted">{t("Dismiss")}</button></div>}</div></div></article>)}</div> : <Empty>{t("No operational signals yet. Add product or service records to generate evidence-based opportunities.")}</Empty>}
    </section>

    <section className="card space-y-4"><header><h2 className="text-lg font-semibold">{t("Business Decision Simulator")}</h2><p className="text-sm text-ink-2">{t("Deterministic arithmetic. Any demand change you enter is clearly treated as a hypothetical assumption.")}</p></header>
      <div className="grid gap-3 sm:grid-cols-3"><label className="block text-sm"><span className="mb-1 block text-ink-2">{t("Scenario")}</span><select value={scenarioKind} onChange={(e) => setScenarioKind(e.target.value)} className="h-10 w-full rounded-xl border border-line bg-surface px-3">{modes.includes("inventory") && <><option value="inventory_discount">{t("Product discount / price change")}</option><option value="restock">{t("Restock quantity")}</option></>}{modes.includes("service") && <option value="service_price">{t("Service price change")}</option>}</select></label>
        <label className="block text-sm"><span className="mb-1 block text-ink-2">{t(isInventoryScenario ? "Product" : "Service")}</span><select value={scenarioName} onChange={(e) => setScenarioName(e.target.value)} className="h-10 w-full rounded-xl border border-line bg-surface px-3"><option value="">{t("Choose…")}</option>{(isInventoryScenario ? data?.inventory ?? [] : data?.services ?? []).map((x) => <option key={x.id} value={x.name}>{x.name}</option>)}</select></label>
        {isRestock ? <Field label={t("Quantity to restock")} type="number" value={quantity} onChange={setQuantity} /> : <Field label={t("Price change (%) — negative is discount")} type="number" value={change} onChange={setChange} />}
        {scenarioKind === "inventory_discount" && <Field label={t("Hypothetical volume uplift (%) — optional")} type="number" value={uplift} onChange={setUplift} />}
      </div><Button onClick={simulate} disabled={busy || !scenarioName}>{t("Run scenario")} <ArrowUpRight className="size-4" /></Button>
      {scenario && <div className="rounded-2xl bg-surface-2 p-4"><h3 className="font-semibold">{t("Scenario result")} · {scenario.name}</h3>{scenario.baseline ? <div className="mt-3 grid gap-3 sm:grid-cols-3"><Metric label={t("Baseline monthly revenue")} value={inr(scenario.baseline.monthly_revenue)} /><Metric label={t("Scenario monthly revenue")} value={inr(scenario.scenario.monthly_revenue)} /><Metric label={t("Contribution change")} value={inr(scenario.change.monthly_contribution)} /></div> : <div className="mt-3 grid gap-3 sm:grid-cols-2"><Metric label={t("Cash outflow") } value={inr(scenario.cash_outflow)} /><Metric label={t("Contribution if all units sell")} value={inr(scenario.estimated_contribution_if_all_sell)} /></div>}<ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-ink-2">{scenario.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul><p className="mt-2 text-xs text-muted">{scenario.classification}</p></div>}
    </section>
  </div>;
}

function Field({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (v: string) => void; type?: string }) { return <label className="block text-sm"><span className="mb-1 block text-ink-2">{label}</span><input type={type} min={type === "number" ? 0 : undefined} step={type === "number" ? "any" : undefined} value={value} onChange={(e) => onChange(e.target.value)} className="h-10 w-full rounded-xl border border-line bg-surface px-3" /></label>; }
function ImportButton({ label, onFile }: { label: string; onFile: (f?: File) => void }) { return <label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-full border border-line px-4 text-sm font-semibold hover:border-brand"><Upload className="size-4" />{label}<input type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(e) => { onFile(e.target.files?.[0]); e.currentTarget.value = ""; }} /></label>; }
function Empty({ children }: { children: React.ReactNode }) { return <div className="rounded-xl border border-dashed border-line p-4 text-sm text-ink-2">{children}</div>; }
function Metric({ label, value }: { label: string; value: string }) { return <div><div className="text-xs text-muted">{label}</div><div className="mt-1 text-lg font-semibold">{value}</div></div>; }
