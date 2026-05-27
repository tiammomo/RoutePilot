import { redirect } from 'next/navigation';

export default function ObservabilityPage() {
  redirect('/workspaces?view=trace');
}

export const dynamic = 'force-dynamic';
