import fs from 'fs/promises';
import path from 'path';
import { QUANT_VISUAL_VALIDATION_RELATIVE_PATH } from '@/lib/quant/artifacts';
import { appendQuantWorkspaceEvent, ensureQuantWorkspace } from '@/lib/quant/workspace';

export type QuantVisualValidationStatus = 'passed' | 'failed' | 'warning';

export interface QuantVisualViewportResult {
  id: 'desktop' | 'mobile';
  width: number;
  height: number;
  screenshotPath: string;
  status: QuantVisualValidationStatus;
  failures: string[];
  warnings: string[];
  metrics: {
    textLength: number;
    svgCount: number;
    canvasCount: number;
    rectCount: number;
    graphicCount: number;
    visibleGraphicCount: number;
    bodyArea: number;
    textBlockCount: number;
    horizontalOverflow: boolean;
    blankLike: boolean;
    hasMarketLanguage: boolean;
    hasDataSourceLanguage: boolean;
  };
}

export interface QuantVisualValidationReport {
  schemaVersion: 1;
  projectId: string;
  requestId?: string | null;
  status: QuantVisualValidationStatus;
  passed: boolean;
  previewUrl: string;
  reportPath: string;
  screenshotDir: string;
  viewports: QuantVisualViewportResult[];
  failures: string[];
  warnings: string[];
  createdAt: string;
  updatedAt: string;
}

const SCREENSHOT_DIR = path.join('tmp', 'visual-checks');
const VIEWPORTS: Array<{ id: 'desktop' | 'mobile'; width: number; height: number }> = [
  { id: 'desktop', width: 1440, height: 900 },
  { id: 'mobile', width: 390, height: 844 },
];

function nowIso() {
  return new Date().toISOString();
}

function safeName(value: string) {
  return value.replace(/[^a-zA-Z0-9_-]/g, '-').slice(0, 80) || 'visual';
}

function uniq(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function statusFromIssues(failures: string[], warnings: string[]): QuantVisualValidationStatus {
  if (failures.length > 0) return 'failed';
  if (warnings.length > 0) return 'warning';
  return 'passed';
}

async function writeReport(projectPath: string, report: QuantVisualValidationReport) {
  await ensureQuantWorkspace(projectPath);
  await fs.writeFile(
    path.join(projectPath, QUANT_VISUAL_VALIDATION_RELATIVE_PATH),
    `${JSON.stringify(report, null, 2)}\n`,
    'utf8'
  );
}

async function validateViewport(params: {
  browser: Awaited<ReturnType<typeof import('playwright').chromium.launch>>;
  projectPath: string;
  projectId: string;
  requestId?: string | null;
  previewUrl: string;
  timestamp: string;
  viewport: { id: 'desktop' | 'mobile'; width: number; height: number };
}): Promise<QuantVisualViewportResult> {
  const page = await params.browser.newPage({
    viewport: {
      width: params.viewport.width,
      height: params.viewport.height,
    },
    deviceScaleFactor: 1,
    isMobile: params.viewport.id === 'mobile',
  });
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedResources: string[] = [];

  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text());
    }
  });
  page.on('pageerror', (error) => {
    pageErrors.push(error.message);
  });
  page.on('response', (response) => {
    const type = response.request().resourceType();
    if (response.status() >= 400 && ['document', 'script', 'stylesheet', 'font', 'image'].includes(type)) {
      failedResources.push(`${response.status()} ${type} ${response.url()}`);
    }
  });

  const screenshotDir = path.join(params.projectPath, SCREENSHOT_DIR);
  await fs.mkdir(screenshotDir, { recursive: true });
  const relativeScreenshotPath = path.posix.join(
    SCREENSHOT_DIR,
    `${safeName(params.projectId)}-${params.viewport.id}-${params.timestamp}.png`
  );
  const absoluteScreenshotPath = path.join(params.projectPath, relativeScreenshotPath);

  const failures: string[] = [];
  const warnings: string[] = [];
  try {
    const response = await page.goto(params.previewUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 45_000,
    });
    if (!response?.ok()) {
      failures.push(`预览地址未返回 2xx：${response?.status() ?? '无响应'}`);
    }
    await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => undefined);
    await page.screenshot({ path: absoluteScreenshotPath, fullPage: true });

    const metrics = await page.evaluate(() => {
      const rects = Array.from(document.querySelectorAll('svg, canvas, rect, path, polyline'));
      const visibleGraphicCount = rects.filter((element) => {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        return rect.width > 4 && rect.height > 4 && style.visibility !== 'hidden' && style.display !== 'none' && Number(style.opacity || '1') > 0;
      }).length;
      const bodyText = document.body.innerText || '';
      const bodyRect = document.body.getBoundingClientRect();
      return {
        textLength: bodyText.replace(/\s+/g, '').length,
        svgCount: document.querySelectorAll('svg').length,
        canvasCount: document.querySelectorAll('canvas').length,
        rectCount: document.querySelectorAll('rect').length,
        graphicCount: rects.length,
        visibleGraphicCount,
        bodyArea: Math.max(0, bodyRect.width * bodyRect.height),
        textBlockCount: Array.from(document.querySelectorAll('h1,h2,h3,p,li,td,th,span')).filter((element) => {
          const text = (element.textContent || '').trim();
          const rect = element.getBoundingClientRect();
          return text.length > 0 && rect.width > 8 && rect.height > 8;
        }).length,
        horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
        blankLike: bodyText.trim().length < 80 && rects.length < 8,
        hasMarketLanguage: /最新价|实时|价格|price|K\s*线|成交量|均线|财务|回撤|波动|净值|持仓|收益|风险/i.test(bodyText),
        hasDataSourceLanguage: /dashboard-data\.json|数据来源|数据信源|信源渠道|source|fetched_at|as_of|更新时间/i.test(bodyText),
      };
    });

    if (metrics.blankLike || metrics.textLength < 120) {
      failures.push('首屏内容过少，页面疑似空白或未完成渲染。');
    }
    if (metrics.horizontalOverflow) {
      failures.push('页面存在横向溢出。');
    }
    if (!metrics.hasMarketLanguage) {
      failures.push('页面缺少行情、K 线、财务、风险或持仓等金融语义。');
    }
    if (!metrics.hasDataSourceLanguage) {
      warnings.push('页面缺少数据信源、更新时间或最终数据文件说明。');
    }
    if (metrics.svgCount + metrics.canvasCount === 0 && metrics.rectCount < 12 && metrics.visibleGraphicCount < 12) {
      failures.push('页面缺少可识别的图表元素。');
    }
    if (metrics.textBlockCount < 6) {
      warnings.push('页面可读文本块较少，可能缺少摘要、指标或说明。');
    }

    warnings.push(...consoleErrors.slice(0, 8).map((item) => `console error：${item}`));
    failures.push(...pageErrors.map((item) => `页面运行错误：${item}`));
    failures.push(...failedResources.map((item) => `资源加载失败：${item}`));

    return {
      ...params.viewport,
      screenshotPath: relativeScreenshotPath,
      status: statusFromIssues(failures, warnings),
      failures: uniq(failures),
      warnings: uniq(warnings),
      metrics,
    };
  } finally {
    await page.close().catch(() => undefined);
  }
}

export async function validateQuantVisualPresentation(params: {
  projectPath: string;
  projectId: string;
  previewUrl: string;
  requestId?: string | null;
}): Promise<QuantVisualValidationReport> {
  const projectPath = path.resolve(params.projectPath);
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const createdAt = nowIso();

  let browser: Awaited<ReturnType<typeof import('playwright').chromium.launch>> | null = null;
  try {
    const { chromium } = await import('playwright');
    browser = await chromium.launch({ headless: true });
    const viewports = await Promise.all(
      VIEWPORTS.map((viewport) =>
        validateViewport({
          browser: browser!,
          projectPath,
          projectId: params.projectId,
          requestId: params.requestId,
          previewUrl: params.previewUrl,
          timestamp,
          viewport,
        })
      )
    );
    const failures = uniq(viewports.flatMap((viewport) => viewport.failures.map((failure) => `${viewport.id}：${failure}`)));
    const warnings = uniq(viewports.flatMap((viewport) => viewport.warnings.map((warning) => `${viewport.id}：${warning}`)));
    const updatedAt = nowIso();
    const status = statusFromIssues(failures, warnings);
    const report: QuantVisualValidationReport = {
      schemaVersion: 1,
      projectId: params.projectId,
      requestId: params.requestId ?? null,
      status,
      passed: status !== 'failed',
      previewUrl: params.previewUrl,
      reportPath: QUANT_VISUAL_VALIDATION_RELATIVE_PATH,
      screenshotDir: SCREENSHOT_DIR,
      viewports,
      failures,
      warnings,
      createdAt,
      updatedAt,
    };
    await writeReport(projectPath, report);
    await appendQuantWorkspaceEvent(projectPath, {
      event_type: 'visual_validation_completed',
      stage: 'validation',
      status: status === 'failed' ? 'error' : status === 'warning' ? 'warning' : 'success',
      run_id: params.requestId ?? undefined,
      artifact_path: QUANT_VISUAL_VALIDATION_RELATIVE_PATH,
      summary: status === 'failed'
        ? `视觉验收未通过：${failures.length} 个阻断项。`
        : status === 'warning'
          ? `视觉验收通过但有 ${warnings.length} 个警告。`
          : '视觉验收通过。',
      created_at: updatedAt,
    });
    return report;
  } catch (error) {
    const updatedAt = nowIso();
    const message = error instanceof Error ? error.message : String(error);
    const report: QuantVisualValidationReport = {
      schemaVersion: 1,
      projectId: params.projectId,
      requestId: params.requestId ?? null,
      status: 'failed',
      passed: false,
      previewUrl: params.previewUrl,
      reportPath: QUANT_VISUAL_VALIDATION_RELATIVE_PATH,
      screenshotDir: SCREENSHOT_DIR,
      viewports: [],
      failures: [`视觉验收执行异常：${message}`],
      warnings: [],
      createdAt,
      updatedAt,
    };
    await writeReport(projectPath, report);
    return report;
  } finally {
    if (browser) {
      await browser.close().catch(() => undefined);
    }
  }
}

export async function readQuantVisualValidationReport(projectPath: string): Promise<QuantVisualValidationReport | null> {
  const content = await fs.readFile(path.join(projectPath, QUANT_VISUAL_VALIDATION_RELATIVE_PATH), 'utf8').catch(() => null);
  if (!content) return null;
  try {
    const parsed = JSON.parse(content);
    return parsed && typeof parsed === 'object' ? parsed as QuantVisualValidationReport : null;
  } catch {
    return null;
  }
}
