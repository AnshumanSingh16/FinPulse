"use client";

import { useContext } from "react";
import { LangProvider } from "@/lib/i18n";
import { DataProvider, DataVersion } from "./data-version";
import { ToastProvider } from "./fx";
import { QuickEntryProvider } from "./quick-entry";
import { Shell } from "./shell";

function WithLang({ children }: { children: React.ReactNode }) {
  const { refresh } = useContext(DataVersion);
  return <LangProvider onChange={refresh}>{children}</LangProvider>;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <DataProvider>
      <WithLang>
        <ToastProvider>
          <QuickEntryProvider>
            <Shell>{children}</Shell>
          </QuickEntryProvider>
        </ToastProvider>
      </WithLang>
    </DataProvider>
  );
}
