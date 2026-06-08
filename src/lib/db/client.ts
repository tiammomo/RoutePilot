import { PrismaClient } from '@prisma/client';

// Prisma Client singleton pattern for Next.js
// Prevents multiple instances in development (hot reload)

const globalForPrisma = global as unknown as { prisma: PrismaClient };

export const prisma =
  globalForPrisma.prisma ||
  new PrismaClient({
    log:
      process.env.NODE_ENV === 'development' && process.env.PRISMA_QUERY_LOG === '1'
        ? ['query', 'error', 'warn']
        : ['error', 'warn'],
  });

if (process.env.NODE_ENV !== 'production') {
  globalForPrisma.prisma = prisma;
}
