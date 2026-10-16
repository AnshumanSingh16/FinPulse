import "@fontsource-variable/inter";
import "./globals.css";
import type { Metadata, Viewport } from "next";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "Munshi — your AI bookkeeper",
  description: "Tell Munshi what happened; it keeps your khata and tells you what to do. English, Hindi, Hinglish.",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: [{ media: "(prefers-color-scheme: light)", color: "#f6f4ef" }, { media: "(prefers-color-scheme: dark)", color: "#101214" }] };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IN" suppressHydrationWarning>
      <head>
        {/* apply the saved theme before first paint (no flash) */}
        <script dangerouslySetInnerHTML={{ __html: `try{var t=localStorage.getItem("finpilot.theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}` }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
