import fs from 'fs/promises';
import path from 'path';
import { appendQuantWorkspaceEvent, ensureQuantWorkspace } from '@/lib/quant/workspace';

type JsonRecord = Record<string, unknown>;
type EvidenceStatus = 'ok' | 'warning' | 'error';

interface DatasetEvidence {
  id: string;
  name: string;
  source: string;
  endpoint: string;
  artifact_path: string;
  row_count: number;
  fetched_at: string | null;
  as_of: string | null;
  missing_fields: string[];
  warnings: string[];
  status: EvidenceStatus;
  critical: boolean;
  fetch?: {
    cache_status?: string;
    cache_ttl_seconds?: number;
    cached_at?: string;
    expires_at?: string;
  };
}

export interface BaselineEvidenceResult {
  created: boolean;
  status?: EvidenceStatus;
  sourceCount?: number;
  reason?: string;
}

const FINAL_DATA_RELATIVE_PATH = 'data_file/final/dashboard-data.json';
const SOURCES_RELATIVE_PATH = 'evidence/sources.json';
const DATA_QUALITY_RELATIVE_PATH = 'evidence/data_quality.json';

function asRecord(value: unknown): JsonRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as JsonRecord;
}

async function readJsonRecord(filePath: string): Promise<JsonRecord | null> {
  try {
    const content = await fs.readFile(filePath, 'utf8');
    const parsed = JSON.parse(content);
    return asRecord(parsed);
  } catch {
    return null;
  }
}

function pickString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
      return String(value);
    }
  }
  return null;
}

function isPresent(value: unknown): boolean {
  if (value === null || value === undefined) {
    return false;
  }
  return typeof value !== 'string' || value.trim().length > 0;
}

function firstArray(...values: unknown[]): unknown[] {
  for (const value of values) {
    if (Array.isArray(value)) {
      return value;
    }
  }
  return [];
}

function buildFetchEvidence(record: JsonRecord | null): DatasetEvidence['fetch'] | undefined {
  const fetchRecord = asRecord(record?.fetch);
  if (!fetchRecord) {
    return undefined;
  }

  const cacheStatus = pickString(fetchRecord.cache_status);
  const cacheTtlRaw = fetchRecord.cache_ttl_seconds;
  const cacheTtlSeconds = typeof cacheTtlRaw === 'number' && Number.isFinite(cacheTtlRaw) ? cacheTtlRaw : undefined;
  const cachedAt = pickString(fetchRecord.cached_at);
  const expiresAt = pickString(fetchRecord.expires_at);

  if (!cacheStatus && cacheTtlSeconds === undefined && !cachedAt && !expiresAt) {
    return undefined;
  }

  return {
    ...(cacheStatus ? { cache_status: cacheStatus } : {}),
    ...(cacheTtlSeconds !== undefined ? { cache_ttl_seconds: cacheTtlSeconds } : {}),
    ...(cachedAt ? { cached_at: cachedAt } : {}),
    ...(expiresAt ? { expires_at: expiresAt } : {}),
  };
}

function missingRequiredGroups(
  record: JsonRecord | null,
  groups: Array<{ label: string; keys: string[] }>
): string[] {
  return groups
    .filter((group) => !record || !group.keys.some((key) => isPresent(record[key])))
    .map((group) => group.label);
}

function buildDataset(params: {
  id: string;
  name: string;
  record: JsonRecord | null;
  rowCount: number;
  source: string;
  endpoint: string;
  critical: boolean;
  generatedAt: string | null;
  missingFields: string[];
  warnings?: string[];
}): DatasetEvidence {
  const fetchedAt = pickString(params.record?.fetched_at, params.generatedAt);
  const asOf = pickString(params.record?.quote_time, params.record?.as_of, fetchedAt);
  const warnings = [...(params.warnings ?? [])];

  if (params.rowCount <= 0) {
    warnings.push('未检测到可用样本。');
  }
  if (params.missingFields.length > 0) {
    warnings.push(`缺失字段：${params.missingFields.join('、')}。`);
  }

  const status: EvidenceStatus =
    params.rowCount <= 0 && params.critical ? 'error' : warnings.length > 0 ? 'warning' : 'ok';

  return {
    id: params.id,
    name: params.name,
    source: params.source,
    endpoint: params.endpoint,
    artifact_path: FINAL_DATA_RELATIVE_PATH,
    row_count: params.rowCount,
    fetched_at: fetchedAt,
    as_of: asOf,
    missing_fields: params.missingFields,
    warnings,
    status,
    critical: params.critical,
    fetch: buildFetchEvidence(params.record),
  };
}

function isUsableSourcesEvidence(value: JsonRecord | null): value is JsonRecord & { sources: unknown[] } {
  const sources = value?.sources;
  if (!Array.isArray(sources) || sources.length === 0) {
    return false;
  }
  return /source|endpoint|fetched_at|as_of|artifact_path/i.test(JSON.stringify(value));
}

function isUsableQualityEvidence(value: JsonRecord | null): value is JsonRecord & { status: EvidenceStatus } {
  const status = value?.status;
  if (!['ok', 'warning', 'error'].includes(typeof status === 'string' ? status : '')) {
    return false;
  }
  return /datasets|checks|missing_fields|warnings|limitations|row_count|fetched_at/i.test(JSON.stringify(value));
}

function buildDatasets(data: JsonRecord, runPlan: JsonRecord | null): DatasetEvidence[] {
  const generatedAt = pickString(data.generatedAt, data.generated_at, data.fetched_at);
  const symbol = pickString(data.symbol, asRecord(data.quote)?.symbol, 'UNKNOWN') ?? 'UNKNOWN';
  const rootSource = pickString(data.source, asRecord(data.quote)?.source, 'unknown') ?? 'unknown';
  const assetType = pickString(data.asset_type, asRecord(data.quote)?.asset_type, 'stock') ?? 'stock';
  const capabilityId = pickString(runPlan?.capabilityId, runPlan?.capability_id);
  const critical = new Set<string>(['quote']);

  if (capabilityId === 'technical_analysis') {
    critical.add('kline');
  } else if (capabilityId === 'fundamental_analysis') {
    critical.add('financials');
  } else if (assetType === 'stock') {
    critical.add('kline');
    critical.add('financials');
  } else {
    critical.add('kline');
  }

  const quote = asRecord(data.quote);
  const kline = asRecord(data.kline) ?? asRecord(data.history);
  const financials = asRecord(data.financials) ?? asRecord(data.fundamentals);
  const fundamentalIndicators = asRecord(data.fundamentalIndicators);
  const announcements = asRecord(data.announcements) ?? asRecord(data.events);
  const technicalIndicators = asRecord(data.technicalIndicators) ?? asRecord(data.indicators);
  const bars = firstArray(kline?.bars, kline?.data, data.bars, data.history);
  const indicatorPoints = firstArray(technicalIndicators?.points, technicalIndicators?.data);
  const reports = firstArray(financials?.reports, financials?.data, data.reports);
  const fundamentalPoints = firstArray(fundamentalIndicators?.points, fundamentalIndicators?.data);
  const announcementRows = firstArray(announcements?.announcements, announcements?.data, data.announcements);

  const firstBar = asRecord(bars[0]);
  const period = pickString(kline?.period, 'daily') ?? 'daily';
  const adjustment = pickString(kline?.adjustment, 'qfq') ?? 'qfq';
  const runPlanRequirements = Array.isArray(runPlan?.dataRequirements)
    ? runPlan.dataRequirements.map((requirement) => String(requirement))
    : [];
  const isStockAsset = assetType === 'stock';
  const requiresTechnicalIndicators =
    Boolean(technicalIndicators) ||
    runPlanRequirements.some((requirement) => requirement.includes('/indicators/technical/'));
  const requiresFundamentalIndicators =
    isStockAsset &&
    (Boolean(fundamentalIndicators) ||
      runPlanRequirements.some((requirement) => requirement.includes('/indicators/fundamental/')));

  const datasets: DatasetEvidence[] = [
    buildDataset({
      id: 'quote',
      name: '实时行情',
      record: quote,
      rowCount: quote ? 1 : 0,
      source: pickString(quote?.source, rootSource) ?? rootSource,
      endpoint: `GET /api/v1/quotes/realtime/${symbol}`,
      critical: critical.has('quote'),
      generatedAt,
      missingFields: missingRequiredGroups(quote, [
        { label: 'symbol', keys: ['symbol', 'code'] },
        { label: 'price', keys: ['price', 'latest', 'close'] },
        { label: 'quote_time/fetched_at', keys: ['quote_time', 'fetched_at', 'as_of'] },
        { label: 'source', keys: ['source'] },
      ]),
    }),
    buildDataset({
      id: 'kline',
      name: '历史 K 线',
      record: kline,
      rowCount: bars.length,
      source: pickString(kline?.source, rootSource) ?? rootSource,
      endpoint: `GET /api/v1/quotes/history/${symbol}?period=${period}&adjustment=${adjustment}`,
      critical: critical.has('kline'),
      generatedAt,
      missingFields: [
        ...missingRequiredGroups(kline, [
          { label: 'fetched_at', keys: ['fetched_at', 'as_of'] },
          { label: 'period', keys: ['period'] },
        ]),
        ...missingRequiredGroups(firstBar, [
          { label: 'trade_date/date', keys: ['trade_date', 'date'] },
          { label: 'close', keys: ['close'] },
        ]),
      ],
    }),
    buildDataset({
      id: 'financials',
      name: '财务摘要',
      record: financials,
      rowCount: reports.length,
      source: pickString(financials?.source, rootSource) ?? rootSource,
      endpoint: `GET /api/v1/fundamentals/financials/${symbol}`,
      critical: critical.has('financials'),
      generatedAt,
      missingFields: [
        ...(isStockAsset
          ? missingRequiredGroups(financials, [{ label: 'fetched_at', keys: ['fetched_at', 'as_of'] }])
          : []),
        ...(isStockAsset
          ? missingRequiredGroups(asRecord(reports[0]), [
              { label: 'report_date/period', keys: ['report_date', 'period', 'date'] },
            ])
          : []),
      ],
    }),
    buildDataset({
      id: 'announcements',
      name: '公告事件',
      record: announcements,
      rowCount: announcementRows.length,
      source: pickString(announcements?.source, rootSource) ?? rootSource,
      endpoint: `GET /api/v1/events/announcements/${symbol}`,
      critical: false,
      generatedAt,
      missingFields: [
        ...(isStockAsset
          ? missingRequiredGroups(announcements, [{ label: 'fetched_at', keys: ['fetched_at', 'as_of'] }])
          : []),
        ...(isStockAsset
          ? missingRequiredGroups(asRecord(announcementRows[0]), [{ label: 'title', keys: ['title', 'notice_title'] }])
          : []),
      ],
    }),
  ];

  if (requiresTechnicalIndicators) {
    datasets.splice(
      2,
      0,
      buildDataset({
        id: 'technical_indicators',
        name: '技术指标',
        record: technicalIndicators,
        rowCount: indicatorPoints.length,
        source: pickString(technicalIndicators?.source, rootSource) ?? rootSource,
        endpoint: `GET /api/v1/indicators/technical/${symbol}`,
        critical: critical.has('kline'),
        generatedAt,
        missingFields: [
          ...missingRequiredGroups(technicalIndicators, [{ label: 'fetched_at', keys: ['fetched_at', 'as_of'] }]),
          ...missingRequiredGroups(asRecord(indicatorPoints.at(-1)), [
            { label: 'date', keys: ['date'] },
            { label: 'ma5/ma20', keys: ['ma5', 'ma20'] },
          ]),
        ],
      })
    );
  }

  if (requiresFundamentalIndicators) {
    const announcementsIndex = datasets.findIndex((dataset) => dataset.id === 'announcements');
    datasets.splice(
      announcementsIndex >= 0 ? announcementsIndex : datasets.length,
      0,
      buildDataset({
        id: 'fundamental_indicators',
        name: '财务衍生指标',
        record: fundamentalIndicators,
        rowCount: fundamentalPoints.length,
        source: pickString(fundamentalIndicators?.source, rootSource) ?? rootSource,
        endpoint: `GET /api/v1/indicators/fundamental/${symbol}`,
        critical: critical.has('financials'),
        generatedAt,
        missingFields: [
          ...missingRequiredGroups(fundamentalIndicators, [{ label: 'fetched_at', keys: ['fetched_at', 'as_of'] }]),
          ...missingRequiredGroups(asRecord(fundamentalPoints[0]), [
            { label: 'report_date', keys: ['report_date'] },
            { label: 'net_margin/roe', keys: ['net_margin', 'weighted_roe'] },
          ]),
        ],
      })
    );
  }

  if (!isStockAsset) {
    return datasets.filter((dataset) => dataset.id !== 'financials' && dataset.id !== 'announcements');
  }

  return datasets;
}

function buildStatus(datasets: DatasetEvidence[]): EvidenceStatus {
  if (datasets.some((dataset) => dataset.status === 'error')) {
    return 'error';
  }
  if (datasets.some((dataset) => dataset.status === 'warning')) {
    return 'warning';
  }
  return 'ok';
}

export async function ensureBaselineEvidenceFiles(
  projectPath: string,
  options: { force?: boolean } = {}
): Promise<BaselineEvidenceResult> {
  await ensureQuantWorkspace(projectPath);

  const sourcesPath = path.join(projectPath, SOURCES_RELATIVE_PATH);
  const qualityPath = path.join(projectPath, DATA_QUALITY_RELATIVE_PATH);
  const existingSources = await readJsonRecord(sourcesPath);
  const existingQuality = await readJsonRecord(qualityPath);

  if (!options.force && isUsableSourcesEvidence(existingSources) && isUsableQualityEvidence(existingQuality)) {
    const sourceCount = Array.isArray(existingSources.sources) ? existingSources.sources.length : undefined;
    const status = typeof existingQuality.status === 'string' ? (existingQuality.status as EvidenceStatus) : undefined;
    return { created: false, status, sourceCount };
  }

  const finalData = await readJsonRecord(path.join(projectPath, FINAL_DATA_RELATIVE_PATH));
  if (!finalData) {
    return {
      created: false,
      reason: `未找到可用于生成 evidence 的 ${FINAL_DATA_RELATIVE_PATH}。`,
    };
  }

  const runPlan = await readJsonRecord(path.join(projectPath, '.quantpilot', 'run_plan.json'));
  const now = new Date().toISOString();
  const runId = pickString(runPlan?.runId, runPlan?.run_id, finalData.runId, finalData.generatedAt, now) ?? now;
  const symbol = pickString(finalData.symbol, asRecord(finalData.quote)?.symbol, 'UNKNOWN') ?? 'UNKNOWN';
  const name = pickString(finalData.name, asRecord(finalData.quote)?.name, symbol) ?? symbol;
  const datasets = buildDatasets(finalData, runPlan);
  const status = buildStatus(datasets);
  const warnings = datasets.flatMap((dataset) =>
    dataset.warnings.map((warning) => `${dataset.name}：${warning}`)
  );
  const limitations = [
    '东方财富等公开接口可能存在延迟，实时性以 fetched_at 与 quote_time/as_of 为准。',
    '本 evidence 为 QuantPilot 平台根据最终数据文件自动生成的基础证据，模型可在后续分析中继续补充更细的数据口径说明。',
  ];

  const sourcesEvidence = {
    schemaVersion: 1,
    runId,
    generated_by: 'quantpilot-platform',
    created_at: now,
    symbol,
    name,
    sources: datasets.map((dataset) => ({
      id: dataset.id,
      dataset: dataset.name,
      source: dataset.source,
      endpoint: dataset.endpoint,
      artifact_path: dataset.artifact_path,
      row_count: dataset.row_count,
      fetched_at: dataset.fetched_at,
      as_of: dataset.as_of,
      status: dataset.status,
      fetch: dataset.fetch,
    })),
  };

  const dataQualityEvidence = {
    schemaVersion: 1,
    runId,
    generated_by: 'quantpilot-platform',
    created_at: now,
    status,
    symbol,
    name,
    datasets: datasets.map(({ critical, ...dataset }) => ({
      ...dataset,
      required: critical,
    })),
    checks: datasets.map((dataset) => ({
      id: `${dataset.id}_quality`,
      dataset: dataset.id,
      status: dataset.status,
      row_count: dataset.row_count,
      missing_fields: dataset.missing_fields,
      summary:
        dataset.status === 'ok'
          ? `${dataset.name}数据形态可用。`
          : `${dataset.name}存在质量提示，需要在页面或结论中说明。`,
    })),
    warnings,
    limitations,
  };

  await fs.mkdir(path.dirname(sourcesPath), { recursive: true });
  await Promise.all([
    fs.writeFile(sourcesPath, `${JSON.stringify(sourcesEvidence, null, 2)}\n`, 'utf8'),
    fs.writeFile(qualityPath, `${JSON.stringify(dataQualityEvidence, null, 2)}\n`, 'utf8'),
  ]);

  await appendQuantWorkspaceEvent(projectPath, {
    event_type: 'data_quality_checked',
    stage: 'data_quality',
    status: status === 'error' ? 'error' : status === 'warning' ? 'warning' : 'success',
    run_id: runId,
    artifact_path: DATA_QUALITY_RELATIVE_PATH,
    summary: `已自动生成数据质量证据，状态：${status}，来源数量：${datasets.length}。`,
    created_at: now,
  });

  return {
    created: true,
    status,
    sourceCount: datasets.length,
  };
}
