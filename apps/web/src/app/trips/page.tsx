import type { Metadata } from "next";

import { TripsScreen } from "@/features/trip-list/TripsScreen";

export const metadata: Metadata = { title: "我的旅行" };

export default function TripsPage() {
  return <TripsScreen />;
}
