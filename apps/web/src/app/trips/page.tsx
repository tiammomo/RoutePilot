import type { Metadata } from "next";

import { TripsScreen } from "@/features/trip-list/TripsScreen";

export const metadata: Metadata = { title: "我的旅行" };

export default async function TripsPage({
  searchParams,
}: {
  searchParams: Promise<{ prompt?: string | string[] }>;
}) {
  const requestedPrompt = (await searchParams).prompt;
  const initialPrompt = typeof requestedPrompt === "string" ? requestedPrompt.slice(0, 2_000) : "";
  return <TripsScreen initialPrompt={initialPrompt} />;
}
