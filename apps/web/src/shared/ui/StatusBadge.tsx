import type { ReactNode } from "react";

export function StatusBadge({ tone = "neutral", children }: { tone?: "neutral" | "brand" | "success" | "warning" | "danger"; children: ReactNode }) {
  return <span className="status-badge" data-tone={tone}>{children}</span>;
}
