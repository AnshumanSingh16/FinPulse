"use client";

import { Check, Copy, MessageCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { post } from "@/lib/api";
import { inr } from "@/lib/format";
import { Button, Loading, Sheet } from "./ui";

interface Draft {
  status: string;
  message?: string;
  customer: string;
  total: number;
  text: string;
  whatsapp: string;
}

export function ReminderSheet({ customer, onClose }: { customer: string | null; onClose: () => void }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [text, setText] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!customer) return;
    setDraft(null);
    setCopied(false);
    post<Draft>("/api/reminder", { customer }).then((d) => {
      setDraft(d);
      setText(d.text ?? "");
    });
  }, [customer]);

  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Sheet open={!!customer} onClose={onClose} title={`Reminder for ${customer ?? ""}`}>
      {!draft ? (
        <Loading label="Drafting…" />
      ) : draft.status !== "ok" ? (
        <p className="text-ink-2">{draft.message}</p>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-ink-2">
            Overdue total <span className="num font-semibold text-ink">{inr(draft.total)}</span>. Edit the message if you like, then send it yourself — FinPilot never sends
            messages on your behalf.
          </p>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={10} className="w-full rounded-2xl border border-line bg-canvas p-4 text-sm leading-relaxed outline-none focus:border-brand" />
          <div className="flex flex-wrap gap-2">
            <Button onClick={copy} variant="secondary">
              {copied ? <Check className="size-4" /> : <Copy className="size-4" />} {copied ? "Copied" : "Copy message"}
            </Button>
            <a href={"https://wa.me/?text=" + encodeURIComponent(text)} target="_blank" rel="noreferrer">
              <Button>
                <MessageCircle className="size-4" /> Open in WhatsApp
              </Button>
            </a>
          </div>
        </div>
      )}
    </Sheet>
  );
}
