"use client";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface">
      <div className="max-w-md text-center">
        <h1 className="mb-4 text-5xl font-bold text-primary">出错了</h1>
        <p className="mb-2 text-sm text-slate-600">
          {error.message || "An unexpected error occurred"}
        </p>
        {error.digest && (
          <p className="mb-6 text-xs text-slate-400">Digest: {error.digest}</p>
        )}
        <button
          onClick={reset}
          className="rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
        >
          重试
        </button>
      </div>
    </div>
  );
}
