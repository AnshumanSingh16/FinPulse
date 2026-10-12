import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex max-w-lg flex-col gap-3">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="text-sm text-muted-foreground">This page doesn&apos;t exist.</p>
      <Link
        href="/"
        className="text-sm font-medium text-primary underline-offset-4 hover:underline"
      >
        Back to overview
      </Link>
    </div>
  );
}
