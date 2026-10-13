import type { Metadata } from "next";
import type { ReactNode } from "react";

import { PersonalProvider } from "@/components/personal/provider";
import { AppShell } from "@/components/shell/app-shell";

import "@fontsource-variable/inter";
import "@fontsource-variable/plus-jakarta-sans";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "FinPulse — Your Financial Life. On Autopilot.", template: "%s · FinPulse" },
  description:
    "An agentic financial copilot that investigates financial decisions, simulates risks, verifies evidence and prepares next steps — with you in control.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en-IN">
      <body>
        <PersonalProvider>
          <AppShell>{children}</AppShell>
        </PersonalProvider>
      </body>
    </html>
  );
}
