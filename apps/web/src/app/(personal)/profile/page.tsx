import type { Metadata } from "next";
import { Suspense } from "react";

import { ProfileEditor } from "@/components/personal/profile-editor";
import { Loading } from "@/components/personal/ui";

export const metadata: Metadata = { title: "Financial Profile" };

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <ProfileEditor />
    </Suspense>
  );
}
