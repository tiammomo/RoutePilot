import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PublicShare } from "./PublicShare";

export const metadata: Metadata = { title: "只读旅行方案", robots: { index: false, follow: false } };

export default async function PublicSharePage({ params }: { params: Promise<{ publicId: string }> }) {
  const { publicId } = await params;
  if (!/^[A-Za-z0-9_-]{3,128}$/.test(publicId)) notFound();
  return <PublicShare publicId={publicId} />;
}
