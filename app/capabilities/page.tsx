import { getCapabilityCenterData } from '@/lib/quant/capability-center';
import CapabilityCenterClient from './CapabilityCenterClient';

export default async function CapabilitiesPage() {
  const data = await getCapabilityCenterData();
  return <CapabilityCenterClient initialData={data} />;
}

export const dynamic = 'force-dynamic';
