#!/usr/bin/env node

const { PrismaClient } = require('@prisma/client');

const prisma = new PrismaClient();

async function main() {
  const databaseUrl = process.env.DATABASE_URL || '';
  const provider = databaseUrl.startsWith('postgresql://') || databaseUrl.startsWith('postgres://')
    ? 'postgresql'
    : 'unsupported';

  console.log(`Database provider: ${provider}`);

  if (provider !== 'postgresql') {
    throw new Error('DATABASE_URL must use PostgreSQL. Run npm run ensure:env to regenerate local database settings.');
  }

  const [{ current_database: database, current_user: user }] =
    await prisma.$queryRaw`SELECT current_database(), current_user`;
  const travelTables =
    await prisma.$queryRaw`
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
        AND table_name IN (
          'travel_commute_edges',
          'travel_wiki_documents',
          'travel_wiki_chunks'
        )
      ORDER BY table_name
    `;

  console.log(`Connected database: ${database}`);
  console.log(`Connected user: ${user}`);
  console.log(`Travel tables: ${travelTables.map((row) => row.table_name).join(', ') || '-'}`);

  await prisma.project.findFirst({ select: { id: true } });
  console.log('Prisma application tables: reachable');
}

main()
  .catch((error) => {
    console.error('[db:doctor] failed:', error instanceof Error ? error.message : error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect().catch(() => {});
  });
