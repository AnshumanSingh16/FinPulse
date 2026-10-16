"use client";

/** Last-resort error screen (when even the app shell fails): shows the real error instead of a blank "couldn't load". */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en-IN">
      <body style={{ fontFamily: "system-ui, sans-serif", background: "#f6f4ef", color: "#1c1d1f", padding: "4rem 1.25rem" }}>
        <div style={{ maxWidth: 520, margin: "0 auto" }}>
          <h1 style={{ fontSize: 24 }}>FinPilot hit a problem</h1>
          <p>Please send this message to whoever set up FinPilot:</p>
          <pre style={{ whiteSpace: "pre-wrap", background: "#ece8df", padding: 16, borderRadius: 16, color: "#c0352b" }}>
            {error.message || String(error)}
            {error.digest ? `\n(${error.digest})` : ""}
          </pre>
          <button onClick={reset} style={{ padding: "10px 20px", borderRadius: 999, border: 0, background: "#0d7a5f", color: "#fff", fontWeight: 600 }}>Try again</button>{" "}
          <button onClick={() => { try { localStorage.clear(); } catch {} location.href = "/"; }} style={{ padding: "10px 20px", borderRadius: 999, border: "1px solid #ccc", background: "#fff", fontWeight: 600 }}>Start over</button>
        </div>
      </body>
    </html>
  );
}
