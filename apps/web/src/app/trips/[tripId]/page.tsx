import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { TripWorkspace } from "@/features/trip-workspace/TripWorkspace";

export const metadata: Metadata = { title: "旅行工作台" };

export default async function TripWorkspacePage({ params }: { params: Promise<{ tripId: string }> }) {
  const { tripId } = await params;
  if (!/^[A-Za-z0-9_-]+$/.test(tripId)) notFound();
  return <TripWorkspace tripId={tripId} />;
}
