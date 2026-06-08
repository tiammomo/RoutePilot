import { execFile } from 'child_process';
import { promisify } from 'util';
import { prisma } from '@/lib/db/client';

const execFileAsync = promisify(execFile);

export interface InfrastructureHealth {
  provider: string;
  databaseUrl: string;
  connected: boolean;
  travelTables: string[];
  docker: {
    available: boolean;
    running: boolean;
    service: { name: string; state: string; status: string; image: string } | null;
    error?: string;
  };
  commands: Record<string, string>;
}

export interface InfrastructureHealthResult {
  success: boolean;
  data: InfrastructureHealth;
  error?: string;
  status: number;
}

const DEFAULT_COMMANDS = {
  start: 'npm run db:up',
  sync: 'npm run prisma:push',
  inspect: 'npm run db:doctor',
  psql: 'npm run db:psql',
};

function maskDatabaseUrl(value: string): string {
  return value.replace(/:\/\/([^:/?#]+):([^@/?#]+)@/, '://$1:***@');
}

async function getDockerComposeStatus(): Promise<InfrastructureHealth['docker']> {
  try {
    const { stdout } = await execFileAsync(
      'docker',
      ['compose', 'ps', 'postgres', '--format', 'json'],
      { cwd: process.cwd(), timeout: 3000 },
    );

    const rows: Array<Record<string, unknown>> = [];
    for (const line of stdout.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      rows.push(JSON.parse(trimmed) as Record<string, unknown>);
    }

    const service = rows[0] ?? null;
    return {
      available: true,
      running: service ? String(service.State ?? '').toLowerCase() === 'running' : false,
      service: service
        ? {
            name: String(service.Name ?? ''),
            state: String(service.State ?? ''),
            status: String(service.Status ?? ''),
            image: String(service.Image ?? ''),
          }
        : null,
    };
  } catch (error) {
    return {
      available: false,
      running: false,
      service: null,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function baseHealth(databaseUrl: string, docker: InfrastructureHealth['docker']): InfrastructureHealth {
  const provider =
    databaseUrl.startsWith('postgresql://') || databaseUrl.startsWith('postgres://')
      ? 'postgresql'
      : 'unsupported';

  return {
    provider,
    databaseUrl: databaseUrl ? maskDatabaseUrl(databaseUrl) : '',
    connected: false,
    travelTables: [],
    docker,
    commands: DEFAULT_COMMANDS,
  };
}

export async function getInfrastructureHealth(): Promise<InfrastructureHealthResult> {
  const databaseUrl = process.env.DATABASE_URL ?? '';
  const docker = await getDockerComposeStatus();
  const provider =
    databaseUrl.startsWith('postgresql://') || databaseUrl.startsWith('postgres://')
      ? 'postgresql'
      : 'unsupported';

  try {
    await prisma.project.findFirst({ select: { id: true } });

    const travelTables =
      provider === 'postgresql'
        ? await prisma.$queryRaw<Array<{ table_name: string }>>`
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN (
                'travel_commute_edges',
                'travel_wiki_documents',
                'travel_wiki_chunks'
              )
            ORDER BY table_name
          `
        : [];

    return {
      success: true,
      status: 200,
      data: {
        ...baseHealth(databaseUrl, docker),
        provider,
        connected: true,
        travelTables: travelTables.map((row) => row.table_name),
      },
    };
  } catch (error) {
    return {
      success: false,
      status: 503,
      data: baseHealth(databaseUrl, docker),
      error: error instanceof Error ? error.message : String(error),
    };
  }
}
