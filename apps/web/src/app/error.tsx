"use client";

import { Button } from "@/components/ui/button";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div role="alert" className="flex max-w-lg flex-col gap-3">
      <h1 className="text-xl font-semibold">Something went wrong</h1>
      <p className="text-sm text-muted-foreground">
        This page failed to render. Try again; if it keeps happening, check the web server logs
        {error.digest ? (
          <>
            {" "}
            for reference <code className="font-mono">{error.digest}</code>
          </>
        ) : null}
        .
      </p>
      <div>
        <Button onClick={reset}>Try again</Button>
      </div>
    </div>
  );
}
