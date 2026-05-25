#!/usr/bin/env node

/**
 * 生成一份浏览器可稳定解析的 Tailwind CSS。
 *
 * next-rspack 目前在 dev 输出里可能把 Tailwind 多声明规则的分号剥掉，
 * 浏览器会因此丢弃大量工具类。这里使用 Tailwind/PostCSS 官方链路生成兜底样式，
 * 让 Rspack 继续负责快速 JS 构建，同时保证页面视觉不退化。
 */

const fs = require('fs/promises');
const path = require('path');
const postcss = require('postcss');
const tailwindcss = require('tailwindcss');
const autoprefixer = require('autoprefixer');

const rootDir = path.join(__dirname, '..');
const inputPath = path.join(rootDir, 'app', 'globals.css');
const outputPath = path.join(rootDir, 'public', 'generated', 'quantpilot-tailwind.css');

async function inlineLocalCssImports(css, fromFile) {
  const localImportPattern = /^@import\s+['"](\.{1,2}\/[^'"]+\.css)['"];\s*$/gm;
  let result = '';
  let cursor = 0;

  for (const match of css.matchAll(localImportPattern)) {
    const [statement, relativePath] = match;
    const start = match.index ?? 0;
    const absolutePath = path.resolve(path.dirname(fromFile), relativePath);
    const importedCss = await fs.readFile(absolutePath, 'utf8');

    result += css.slice(cursor, start);
    result += `\n/* 内联：${relativePath} */\n${importedCss}\n`;
    cursor = start + statement.length;
  }

  result += css.slice(cursor);
  return result;
}

async function buildStableCss({ silent = false } = {}) {
  const rawCss = await fs.readFile(inputPath, 'utf8');
  const css = await inlineLocalCssImports(rawCss, inputPath);
  const result = await postcss([
    tailwindcss(path.join(rootDir, 'tailwind.config.ts')),
    autoprefixer,
  ]).process(css, {
    from: inputPath,
    to: outputPath,
  });

  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, result.css);

  if (!silent) {
    console.log(`✅ Stable Tailwind CSS generated: ${path.relative(rootDir, outputPath)}`);
  }

  return outputPath;
}

if (require.main === module) {
  buildStableCss().catch((error) => {
    console.error('[styles] Failed:', error instanceof Error ? error.message : error);
    process.exit(1);
  });
}

module.exports = {
  buildStableCss,
};
