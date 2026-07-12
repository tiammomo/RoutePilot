"use client";

import { useRouter } from "next/navigation";

import { TripCreateForm } from "@/features/trip-create/TripCreateForm";

export function HomeQuickStart() {
  const router = useRouter();
  return (
    <TripCreateForm
      variant="hero"
      onCreated={(trip) => router.push(`/trips/${trip.trip_id}`)}
    />
  );
}
