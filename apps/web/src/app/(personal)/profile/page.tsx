import type { Metadata } from "next";

import { ProfileEditor } from "@/components/personal/profile-editor";

export const metadata: Metadata = { title: "Financial Profile" };

// Rendered per request: these pages read the URL (search params) and per-session data.
export const dynamic = "force-dynamic";

export default function Page() {
  return <ProfileEditor />;
}
