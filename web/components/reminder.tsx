"use client";

import { Check, Copy, MessageCircle, Phone } from "lucide-react";
import { useEffect, useState } from "react";
import { get, post } from "@/lib/api";
import { inr } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { Avatar } from "./cat";
import { Button, Loading, Sheet } from "./ui";

interface Draft {
  status?: string;
  message?: string;
  customer: string;
  total: number;
  text: string;
  phone: string | null;
  whatsapp: string;
  oldest_days_late?: number;
}

function wa(text: string, phone: string | null) {
  return `https://wa.me/${phone ?? ""}?text=${encodeURIComponent(text)}`;
}

export function ReminderSheet({ customer, onClose }: { customer: string | null; onClose: () => void }) {
  const { t } = useT();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [text, setText] = useState("");
  const [phone, setPhone] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!customer) return;
    setDraft(null);
    setCopied(false);
    post<Draft>("/api/reminder", { customer }).then((d) => {
      setDraft(d);
      setText(d.text ?? "");
      setPhone(d.phone ?? "");
    });
  }, [customer]);

  const savePhone = async () => {
    if (customer && phone) await post("/api/person/contact", { name: customer, phone });
  };

  return (
    <Sheet open={!!customer} onClose={onClose} title={`${t("Send reminder")} · ${customer ?? ""}`}>
      {!draft ? (
        <Loading />
      ) : draft.status !== "ok" ? (
        <p className="text-ink-2">{draft.message}</p>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-ink-2">
            <span className="num text-lg font-bold text-bad">{inr(draft.total)}</span> {t("overdue")} · FinPilot never sends messages on your behalf.
          </p>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={9} className="w-full rounded-2xl border border-line bg-canvas p-4 text-sm leading-relaxed outline-none focus:border-brand" />
          <label className="flex items-center gap-2 rounded-xl border border-line px-3">
            <Phone className="size-4 text-muted" />
            <input value={phone} onChange={(e) => setPhone(e.target.value)} onBlur={savePhone} placeholder={t("Phone (WhatsApp)")} inputMode="tel" className="h-10 flex-1 bg-transparent text-sm outline-none" />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              onClick={async () => {
                await navigator.clipboard.writeText(text);
                setCopied(true);
              }}
            >
              {copied ? <Check className="size-4" /> : <Copy className="size-4" />} {t(copied ? "Copied" : "Copy message")}
            </Button>
            <a href={wa(text, phone.replace(/\D/g, "").length === 10 ? "91" + phone.replace(/\D/g, "") : phone.replace(/\D/g, "") || null)} target="_blank" rel="noreferrer" onClick={savePhone}>
              <Button className="!bg-[#25d366] hover:!bg-[#1ebe5a]">
                <MessageCircle className="size-4" /> {t("Open in WhatsApp")}
              </Button>
            </a>
          </div>
        </div>
      )}
    </Sheet>
  );
}

export function BulkReminders({ onClose }: { onClose: () => void }) {
  const { t } = useT();
  const [list, setList] = useState<Draft[] | null>(null);
  const [sent, setSent] = useState<Record<string, boolean>>({});
  useEffect(() => {
    get<Draft[]>("/api/reminders").then(setList);
  }, []);
  return (
    <Sheet open onClose={onClose} title={t("Remind all overdue")} wide>
      {!list ? (
        <Loading />
      ) : list.length === 0 ? (
        <p className="py-6 text-center text-ink-2">{t("Nothing overdue — great collections!")}</p>
      ) : (
        <ul className="space-y-3">
          {list.map((d) => (
            <li key={d.customer} className="flex items-center gap-3 rounded-2xl border border-line p-3">
              <Avatar name={d.customer} />
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{d.customer}</p>
                <p className="text-xs text-muted">
                  <span className="num font-semibold text-bad">{inr(d.total)}</span> · {d.oldest_days_late} {t("days late")}
                </p>
              </div>
              <a href={d.whatsapp} target="_blank" rel="noreferrer" onClick={() => setSent((s) => ({ ...s, [d.customer]: true }))}>
                <Button size="sm" className={sent[d.customer] ? "!bg-good" : "!bg-[#25d366] hover:!bg-[#1ebe5a]"}>
                  {sent[d.customer] ? <Check className="size-4" /> : <MessageCircle className="size-4" />} WhatsApp
                </Button>
              </a>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}
