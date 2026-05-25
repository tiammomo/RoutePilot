#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const rootDir = path.join(__dirname, '..');
const outputDir = path.join(rootDir, 'tmp', 'visual-checks');
const timestamp = new Date().toISOString().replace(/[:.]/g, '-');

const projectId = process.env.PROJECT_ID || process.argv[2] || '';
const baseUrl = (process.env.QUANTPILOT_WEB_URL || 'http://localhost:3000').replace(/\/+$/, '');
const cli = process.env.CLI || 'claude';
const model = process.env.MODEL || 'MiniMax-M2.7';

function fail(message, details = []) {
  console.error(`\n❌ 项目可视化截图检查失败：${message}`);
  for (const detail of details) {
    console.error(`- ${detail}`);
  }
  process.exitCode = 1;
}

async function main() {
  if (!projectId) {
    fail('缺少 PROJECT_ID。用法：PROJECT_ID=project-xxx npm run check:project-visual');
    return;
  }

  fs.mkdirSync(outputDir, { recursive: true });
  const screenshotPath = path.join(outputDir, `${projectId}-chat-${timestamp}.png`);
  const previewScreenshotPath = path.join(outputDir, `${projectId}-preview-${timestamp}.png`);
  const url = `${baseUrl}/${projectId}/chat?cli=${encodeURIComponent(cli)}&model=${encodeURIComponent(model)}`;

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
    const resourceType = response.request().resourceType();
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
      fail(`聊天页请求异常：${response ? response.status() : '无响应'}`);
      return;
    }

    await page.waitForFunction(
      () => Object.getOwnPropertyNames(document.querySelector('button') || {}).some((key) => key.startsWith('__react')),
      { timeout: 12000 }
    ).catch(() => {});

    await page.waitForSelector('iframe[src]', { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(2000);
    await page.screenshot({ path: screenshotPath, fullPage: true });

    const pageInfo = await page.evaluate(() => {
      const iframe = document.querySelector('iframe');
      const button = document.querySelector('button');
      return {
        hydrated: Boolean(
          button &&
            Object.getOwnPropertyNames(button).some((key) => key.startsWith('__react'))
        ),
        iframeSrc: iframe?.getAttribute('src') || null,
        iframeCount: document.querySelectorAll('iframe').length,
        text: document.body.innerText,
      };
    });

    const frame = page.frames().find((candidate) => {
      const frameUrl = candidate.url();
      return Boolean(pageInfo.iframeSrc && frameUrl.startsWith(pageInfo.iframeSrc));
    });

    const frameInfo = frame
      ? await frame.evaluate(() => ({
          text: document.body.innerText,
          svgCount: document.querySelectorAll('svg').length,
          rectCount: document.querySelectorAll('rect').length,
          canvasCount: document.querySelectorAll('canvas').length,
        }))
      : null;

    if (frame) {
      await page.screenshot({ path: previewScreenshotPath, fullPage: true });
    }

    const problems = [];
    if (!pageInfo.hydrated) {
      problems.push('聊天页未完成 React 客户端水合，按钮事件不会生效');
    }
    if (!pageInfo.iframeSrc) {
      problems.push('右侧没有自动展示预览 iframe');
    }
    if (!frameInfo) {
      problems.push('未能读取预览 iframe 内容');
    } else {
      if (!/最新价|实时|价格|price/i.test(frameInfo.text)) {
        problems.push('预览页面缺少价格或行情信息');
      }
      if (!/K\s*线|蜡烛|开盘|最高|最低|收盘|成交量/i.test(frameInfo.text)) {
        problems.push('预览页面缺少 K 线或成交量结构');
      }
      if (frameInfo.svgCount + frameInfo.canvasCount === 0 && frameInfo.rectCount < 20) {
        problems.push('预览页面缺少可识别图表元素');
      }
      if (!/dashboard-data\.json|数据来源|source/i.test(frameInfo.text)) {
        problems.push('预览页面缺少数据来源或最终数据文件说明');
      }
    }
    problems.push(...failedResources.map((item) => `静态资源失败：${item}`));
    problems.push(...pageErrors.map((item) => `页面运行错误：${item}`));

    if (problems.length > 0) {
      fail('关键可视化结构不符合预期', problems);
      console.error(`聊天页截图：${screenshotPath}`);
      console.error(`预览截图：${previewScreenshotPath}`);
      return;
    }

    if (consoleErrors.length > 0) {
      console.warn(`⚠️  检测到 ${consoleErrors.length} 条浏览器 console error，未阻断检查。`);
      for (const item of consoleErrors.slice(0, 5)) {
        console.warn(`- ${item}`);
      }
    }

    console.log('✅ 项目可视化截图检查通过');
    console.log(`URL：${url}`);
    console.log(`iframe：${pageInfo.iframeSrc}`);
    console.log(`聊天页截图：${screenshotPath}`);
    console.log(`预览截图：${previewScreenshotPath}`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  fail(error instanceof Error ? error.message : String(error));
});
