import "@fontsource-variable/inter";
import "./globals.css";
import type { Metadata, Viewport } from "next";
import { DataProvider } from "@/components/data-version";
import { Shell } from "@/components/shell";

export const metadata: Metadata = {
  title: "FinPilot — your business, in plain words",
  description: "See your cash, chase what you're owed, and check big decisions before you make them.",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#ffffff" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IN">
      <body>
        <DataProvider>
          <Shell>{children}</Shell>
        </DataProvider>
      </body>
    </html>
  );
}
