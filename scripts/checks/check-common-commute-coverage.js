#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const rootDir = path.join(__dirname, '..', '..');
const reportPath = path.join(rootDir, 'travel-data', 'analysis', 'common-commute-coverage.json');

function main() {
  if (!fs.existsSync(reportPath)) {
    throw new Error('common commute coverage report is missing. Run npm run travel:commute:analyze-common first.');
  }
  const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
  const missing = Array.isArray(report.pairs) ? report.pairs.filter((pair) => pair.needs_backfill) : [];
  console.log('[common-commute-coverage] report ready');
  console.log(`coverage=${report.covered_pair_count}/${report.pair_count} (${Math.round(Number(report.coverage_rate || 0) * 100)}%)`);
  console.log(`missing=${missing.length}`);
  for (const pair of missing.slice(0, 5)) {
    console.log(`- ${pair.origin_name} -> ${pair.destination_name} (${pair.frequency}x)`);
  }
}

try {
  main();
} catch (error) {
  console.error('[common-commute-coverage] failed:', error);
  process.exit(1);
}
