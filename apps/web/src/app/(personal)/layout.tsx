import type { ReactNode } from "react";

import { PersonalProvider } from "@/components/personal/provider";

export default function PersonalLayout({ children }: { children: ReactNode }) {
  return <PersonalProvider>{children}</PersonalProvider>;
}
