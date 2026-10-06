import { CircleAlert, CircleCheck, CircleX, LoaderCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";

export type StatusTone = "ok" | "warning" | "error" | "pending";

const TONES = {
  ok: { variant: "success", Icon: CircleCheck },
  warning: { variant: "warning", Icon: CircleAlert },
  error: { variant: "destructive", Icon: CircleX },
  pending: { variant: "secondary", Icon: LoaderCircle },
} as const;

/** Status is always conveyed by icon + text, never by colour alone. */
export function StatusBadge({ tone, label }: { tone: StatusTone; label: string }) {
  const { variant, Icon } = TONES[tone];
  return (
    <Badge variant={variant}>
      <Icon aria-hidden className={tone === "pending" ? "animate-spin" : undefined} />
      {label}
    </Badge>
  );
}
