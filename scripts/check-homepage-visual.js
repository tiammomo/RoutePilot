#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const rootDir = path.join(__dirname, '..');
const url = process.env.HOMEPAGE_URL || 'http://localhost:3000/';
const outputDir = path.join(rootDir, 'tmp', 'visual-checks');
const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
const screenshotPath = path.join(outputDir, `homepage-${timestamp}.png`);

function fail(message, details = []) {
  console.error(`\n❌ 首页截图检查失败：${message}`);
  for (const detail of details) {
    console.error(`- ${detail}`);
  }
  process.exitCode = 1;
}

async function assertVisible(page, selector, label) {
  const locator = page.locator(selector).first();
  try {
    await locator.waitFor({ state: 'visible', timeout: 5000 });
    return true;
  } catch {
    return `${label} 不可见：${selector}`;
  }
}

async function assertAnyVisible(page, selectors, label) {
  for (const selector of selectors) {
    const result = await assertVisible(page, selector, label);
    if (result === true) {
      return true;
    }
  }
  return `${label} 不可见：${selectors.join(' 或 ')}`;
}

async function main() {
  fs.mkdirSync(outputDir, { recursive: true });

  const consoleErrors = [];
  const pageErrors = [];
  const failedResources = [];

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  });

  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text());
    }
  });

  page.on('pageerror', (error) => {
    pageErrors.push(error.message);
  });

  page.on('response', (response) => {
    const request = response.request();
    const resourceType = request.resourceType();
    if (
      response.status() >= 400 &&
      ['document', 'script', 'stylesheet', 'image', 'font'].includes(resourceType)
    ) {
      failedResources.push(`${response.status()} ${resourceType} ${response.url()}`);
    }
  });

  try {
    const response = await page.goto(url, {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    });

    if (!response || !response.ok()) {
      fail(`首页请求异常：${response ? response.status() : '无响应'}`);
      return;
    }

    await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
    await page.waitForFunction(
      () =>
        Object.getOwnPropertyNames(document.querySelector('button') || {}).some((key) =>
          key.startsWith('__react')
        ),
      { timeout: 12000 }
    ).catch(() => {});
    await page.screenshot({ path: screenshotPath, fullPage: true });

    const hydrated = await page.evaluate(() =>
      Object.getOwnPropertyNames(document.querySelector('button') || {}).some((key) =>
        key.startsWith('__react')
      )
    );

    const checks = await Promise.all([
      assertVisible(page, 'h1:has-text("QuantPilot"), h2:has-text("QuantPilot")', 'QuantPilot 标识'),
      assertVisible(page, 'text=选择能力，描述需求', '首页说明文案'),
      assertVisible(page, 'textarea[placeholder*="请输入任务"]', '任务输入框'),
      assertAnyVisible(page, ['button[title="打开任务记录"]', 'text=任务记录'], '任务记录入口'),
      assertVisible(page, 'text=分析能力', '左侧分析能力区'),
    ]);

    const visibleFailures = checks.filter((result) => result !== true);
    const problems = [
      ...(hydrated ? [] : ['首页未完成 React 客户端水合，按钮事件不会生效']),
      ...visibleFailures,
      ...failedResources.map((item) => `静态资源失败：${item}`),
      ...pageErrors.map((item) => `页面运行错误：${item}`),
    ];

    if (problems.length > 0) {
      fail('关键页面元素或资源不符合预期', problems);
      console.error(`截图已保存：${screenshotPath}`);
      return;
    }

    if (consoleErrors.length > 0) {
      console.warn(`⚠️  检测到 ${consoleErrors.length} 条浏览器 console error，未阻断截图检查。`);
      for (const item of consoleErrors.slice(0, 5)) {
        console.warn(`- ${item}`);
      }
    }

    console.log('✅ 首页截图检查通过');
    console.log(`URL：${url}`);
    console.log(`截图：${screenshotPath}`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  fail(error instanceof Error ? error.message : String(error));
});
