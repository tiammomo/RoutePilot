#!/usr/bin/env node

process.env.SKIP_DB_SYNC = process.env.SKIP_DB_SYNC || '1';
process.env.TRAVELPILOT_WARMUP = process.env.TRAVELPILOT_WARMUP || '1';

console.log('[dev:travel] SKIP_DB_SYNC=1, TRAVELPILOT_WARMUP=1');
console.log('[dev:travel] If the Node process grows beyond 1GB after long HMR sessions, restart this command.');

const { startWebDevServer } = require('./run-web');

startWebDevServer({
  preferredPort: Number.parseInt(process.env.PORT || '3000', 10),
  passthrough: process.argv.slice(2),
  stdio: 'inherit',
}).catch((error) => {
  console.error('\n[dev:travel] Failed to launch dev server');
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
