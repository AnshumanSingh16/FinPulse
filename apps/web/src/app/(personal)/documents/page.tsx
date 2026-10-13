import type { Metadata } from "next";

import { DocumentCenter } from "@/components/personal/document-center";

export const metadata: Metadata = { title: "Documents" };

// Rendered per request: these pages read the URL (search params) and per-session data.
export const dynamic = "force-dynamic";

export default function Page() {
  return <DocumentCenter />;
}
