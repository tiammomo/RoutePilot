/**
 * Validates that all scaffold page templates compile under Next.js.
 *
 * Extracts each template string, writes it to a temporary Next.js project,
 * and runs `next build` to catch JSX/TS errors that `tsc --noEmit` on the
 * platform code cannot catch (because templates are raw strings).
 *
 * Usage: npx tsx scripts/build/validate-scaffold-templates.ts
 */

import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { execSync } from 'child_process';

const SCAFFOLD_TS = path.join(process.cwd(), 'src', 'lib', 'utils', 'scaffold.ts');

interface TemplateEntry {
  name: string;
  pageContent: string;
  cssContent: string;
}

async function extractTemplates(): Promise<TemplateEntry[]> {
  const source = await fs.readFile(SCAFFOLD_TS, 'utf8');

  const entries: TemplateEntry[] = [];

  // Extract holdingAnalysisPageTemplate
  const holdingMatch = source.match(/function holdingAnalysisPageTemplate\(\) \{\s*return `([\s\S]*?)`;\s*\}/);
  if (holdingMatch) {
    const cssMatch = source.match(/function holdingAnalysisCss\(\) \{\s*return `([\s\S]*?)`;\s*\}/);
    entries.push({
      name: 'holdingAnalysis',
      pageContent: holdingMatch[1],
      cssContent: cssMatch ? cssMatch[1] : '',
    });
  }

  // Extract comparisonPageTemplate
  const comparisonMatch = source.match(/function comparisonPageTemplate\(\) \{\s*return `([\s\S]*?)`;\s*\}/);
  if (comparisonMatch) {
    const cssMatch = source.match(/function comparisonCss\(\) \{\s*return `([\s\S]*?)`;\s*\}/);
    entries.push({
      name: 'comparison',
      pageContent: comparisonMatch[1],
      cssContent: cssMatch ? cssMatch[1] : '',
    });
  }

  // Extract stockSelectionPageTemplate
  const selectionMatch = source.match(/function stockSelectionPageTemplate\(\) \{\s*return `([\s\S]*?)`;\s*\}/);
  if (selectionMatch) {
    const cssMatch = source.match(/function stockSelectionCss\(\) \{\s*return `([\s\S]*?)`;\s*\}/);
    entries.push({
      name: 'stockSelection',
      pageContent: selectionMatch[1],
      cssContent: cssMatch ? cssMatch[1] : '',
    });
  }

  return entries;
}

async function validateTemplate(entry: TemplateEntry, tmpDir: string): Promise<{ name: string; ok: boolean; error?: string }> {
  const projectDir = path.join(tmpDir, entry.name);
  await fs.mkdir(path.join(projectDir, 'app'), { recursive: true });

  // Write package.json
  await fs.writeFile(
    path.join(projectDir, 'package.json'),
    JSON.stringify(
      {
        name: `template-check-${entry.name}`,
        private: true,
        version: '0.1.0',
        scripts: { build: 'next build' },
        dependencies: {
          next: '^16.2.6',
          react: '^19.0.0',
          'react-dom': '^19.0.0',
          '@types/react': '^19.0.0',
          '@types/node': '^22.0.0',
          typescript: '^5.0.0',
        },
      },
      null,
      2
    ),
    'utf8'
  );

  // Write tsconfig.json
  await fs.writeFile(
    path.join(projectDir, 'tsconfig.json'),
    JSON.stringify(
      {
        compilerOptions: {
          target: 'ES2017',
          lib: ['dom', 'dom.iterable', 'esnext'],
          allowJs: true,
          skipLibCheck: true,
          strict: true,
          noEmit: true,
          esModuleInterop: true,
          module: 'esnext',
          moduleResolution: 'bundler',
          resolveJsonModule: true,
          isolatedModules: true,
          jsx: 'react-jsx',
          plugins: [{ name: 'next' }],
          paths: { '@/*': ['./*'] },
        },
        include: ['next-env.d.ts', '**/*.ts', '**/*.tsx'],
        exclude: ['node_modules'],
      },
      null,
      2
    ),
    'utf8'
  );

  // Write next.config.ts
  await fs.writeFile(
    path.join(projectDir, 'next.config.ts'),
    `import type { NextConfig } from 'next';\nconst config: NextConfig = {};\nexport default config;\n`,
    'utf8'
  );

  // Write page.tsx
  await fs.writeFile(path.join(projectDir, 'app', 'page.tsx'), entry.pageContent, 'utf8');

  // Write globals.css
  const baseCss = `
:root {
  --bg: #f8fafc;
  --panel: #ffffff;
  --ink: #0f172a;
  --muted: #64748b;
  --line: #e2e8f0;
  --red: #dc2626;
  --green: #16a34a;
  --blue: #2563eb;
  --surface-1: #f8fafc;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
}
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px; text-align: left; border-bottom: 1px solid var(--line); font-size: 14px; }
th { font-weight: 600; color: var(--muted); }
.empty-state { color: var(--muted); padding: 16px; }
`;
  await fs.writeFile(path.join(projectDir, 'app', 'globals.css'), `${baseCss}\n${entry.cssContent}`, 'utf8');

  // Write layout.tsx
  await fs.writeFile(
    path.join(projectDir, 'app', 'layout.tsx'),
    `import type { Metadata } from 'next';\nimport './globals.css';\nexport const metadata: Metadata = { title: 'Template Check' };\nexport default function RootLayout({ children }: { children: React.ReactNode }) { return <html lang="zh-CN"><body>{children}</body></html>; }\n`,
    'utf8'
  );

  // Install dependencies and build
  try {
    execSync('npm install --legacy-peer-deps', { cwd: projectDir, stdio: 'pipe', timeout: 60000 });
    execSync('node node_modules/.bin/next build', { cwd: projectDir, stdio: 'pipe', timeout: 60000 });
    return { name: entry.name, ok: true };
  } catch (err: unknown) {
    const stderr = err instanceof Error && 'stderr' in err ? String((err as { stderr?: Buffer }).stderr ?? '') : '';
    const stdout = err instanceof Error && 'stdout' in err ? String((err as { stdout?: Buffer }).stdout ?? '') : '';
    const message = (stderr + stdout).slice(-2000) || String(err);
    return { name: entry.name, ok: false, error: message };
  }
}

async function main() {
  console.log('[validate-scaffold-templates] Extracting templates from scaffold.ts...');
  const entries = await extractTemplates();
  console.log(`Found ${entries.length} templates to validate: ${entries.map((e) => e.name).join(', ')}`);

  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'qp-template-check-'));
  console.log(`Working in ${tmpDir}`);

  let failed = 0;
  for (const entry of entries) {
    console.log(`\n[${entry.name}] Validating...`);
    const result = await validateTemplate(entry, tmpDir);
    if (result.ok) {
      console.log(`[${entry.name}] PASSED`);
    } else {
      failed++;
      console.log(`[${entry.name}] FAILED`);
      console.log(result.error);
    }
  }

  await fs.rm(tmpDir, { recursive: true, force: true });
  console.log(`\nDone: ${entries.length - failed} passed, ${failed} failed`);
  process.exit(failed > 0 ? 1 : 0);
}

main();
