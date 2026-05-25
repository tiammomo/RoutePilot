import { createHash } from 'crypto';
import fs from 'fs/promises';
import path from 'path';
import { createSdkMcpServer, tool } from '@anthropic-ai/claude-agent-sdk';
import { z } from 'zod';

const PORTFOLIO_SCREENSHOT_FIELDS = [
  'account_total_asset',
  'cash_available',
  'market_value',
  'daily_pnl',
  'total_pnl',
  'position_ratio',
  'holdings[].name',
  'holdings[].symbol_if_visible_or_resolved',
  'holdings[].quantity',
  'holdings[].cost_price',
  'holdings[].current_price',
  'holdings[].market_value',
  'holdings[].pnl',
  'holdings[].pnl_percent',
];

type AttachmentRecord = {
  id?: string;
  name?: string;
  absolutePath?: string;
  path?: string;
  url?: string;
  publicUrl?: string | null;
  mimeType?: string | null;
  size?: number | null;
};

function isInside(parent: string, candidate: string): boolean {
  const relative = path.relative(parent, candidate);
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

function resolveInsideProject(projectPath: string, inputPath: string): string {
  const resolved = path.isAbsolute(inputPath)
    ? path.resolve(inputPath)
    : path.resolve(projectPath, inputPath);
  if (!isInside(projectPath, resolved)) {
    throw new Error(`图片路径必须位于当前生成项目内：${inputPath}`);
  }
  return resolved;
}

function inferMimeType(filePath: string, buffer: Buffer): string {
  const lower = filePath.toLowerCase();
  if (buffer.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) || lower.endsWith('.png')) {
    return 'image/png';
  }
  if ((buffer[0] === 0xff && buffer[1] === 0xd8) || lower.endsWith('.jpg') || lower.endsWith('.jpeg')) {
    return 'image/jpeg';
  }
  if (buffer.subarray(0, 3).toString('ascii') === 'GIF' || lower.endsWith('.gif')) {
    return 'image/gif';
  }
  if (buffer.subarray(0, 4).toString('ascii') === 'RIFF' && buffer.subarray(8, 12).toString('ascii') === 'WEBP') {
    return 'image/webp';
  }
  return 'application/octet-stream';
}

function readImageSize(buffer: Buffer, mimeType: string): { width: number | null; height: number | null } {
  if (mimeType === 'image/png' && buffer.length >= 24) {
    return {
      width: buffer.readUInt32BE(16),
      height: buffer.readUInt32BE(20),
    };
  }

  if (mimeType === 'image/gif' && buffer.length >= 10) {
    return {
      width: buffer.readUInt16LE(6),
      height: buffer.readUInt16LE(8),
    };
  }

  if (mimeType === 'image/jpeg' && buffer.length > 4) {
    let offset = 2;
    while (offset < buffer.length) {
      if (buffer[offset] !== 0xff) {
        offset += 1;
        continue;
      }
      const marker = buffer[offset + 1];
      const length = buffer.readUInt16BE(offset + 2);
      const isSofMarker =
        marker === 0xc0 ||
        marker === 0xc1 ||
        marker === 0xc2 ||
        marker === 0xc3 ||
        marker === 0xc5 ||
        marker === 0xc6 ||
        marker === 0xc7 ||
        marker === 0xc9 ||
        marker === 0xca ||
        marker === 0xcb ||
        marker === 0xcd ||
        marker === 0xce ||
        marker === 0xcf;
      if (isSofMarker && offset + 8 < buffer.length) {
        return {
          height: buffer.readUInt16BE(offset + 5),
          width: buffer.readUInt16BE(offset + 7),
        };
      }
      offset += 2 + length;
    }
  }

  return { width: null, height: null };
}

async function readAttachmentContext(projectPath: string, contextPath: string): Promise<{
  contextPath: string;
  attachments: AttachmentRecord[];
}> {
  const absoluteContextPath = resolveInsideProject(projectPath, contextPath);
  const content = await fs.readFile(absoluteContextPath, 'utf8');
  const parsed = JSON.parse(content) as { attachments?: AttachmentRecord[] };
  return {
    contextPath: path.relative(projectPath, absoluteContextPath).replaceAll(path.sep, '/'),
    attachments: Array.isArray(parsed.attachments) ? parsed.attachments : [],
  };
}

async function inspectImage(projectPath: string, attachment: AttachmentRecord, index: number) {
  const sourcePath = attachment.absolutePath ?? attachment.path;
  if (!sourcePath) {
    throw new Error(`附件 ${attachment.name ?? index + 1} 缺少 path/absolutePath`);
  }

  const absolutePath = resolveInsideProject(projectPath, sourcePath);
  const buffer = await fs.readFile(absolutePath);
  const stat = await fs.stat(absolutePath);
  const mimeType = attachment.mimeType ?? inferMimeType(absolutePath, buffer);
  const size = readImageSize(buffer, mimeType);
  const sha256 = createHash('sha256').update(buffer).digest('hex');

  return {
    id: attachment.id ?? `image-${index + 1}`,
    name: attachment.name ?? path.basename(absolutePath),
    path: path.relative(projectPath, absolutePath).replaceAll(path.sep, '/'),
    absolutePath,
    url: attachment.url ?? null,
    publicUrl: attachment.publicUrl ?? null,
    mimeType,
    size: stat.size,
    width: size.width,
    height: size.height,
    sha256,
  };
}

function buildExtractionPayload(params: {
  projectPath: string;
  contextPath: string;
  prompt?: string;
  inspectedImages: Awaited<ReturnType<typeof inspectImage>>[];
}) {
  return {
    schemaVersion: 1,
    tool: 'quant-image-extraction',
    status: 'metadata_ready',
    createdAt: new Date().toISOString(),
    projectPath: params.projectPath,
    attachmentContextPath: params.contextPath,
    prompt: params.prompt ?? null,
    images: params.inspectedImages,
    visualRecognition: {
      status: 'requires_vision_provider',
      reason:
        'QuantPilot 已确认图片文件、路径、格式、尺寸和哈希。当前本地工具不内置 OCR，视觉字段需要继续调用 MiniMax understand_image MCP 或后续接入的 OCR/Python 提取器。',
      preferredNextTool: 'mcp__MiniMax__understand_image',
      fallbackRule: '如果视觉工具不可用，所有截图字段必须保留 null，并在 evidence/data_quality.json 中列出需要用户确认的字段。',
    },
    imageExtraction: {
      source: 'uploaded_image',
      extractedFields: {
        account_total_asset: null,
        cash_available: null,
        market_value: null,
        daily_pnl: null,
        total_pnl: null,
        position_ratio: null,
        holdings: [],
      },
      needs_manual_confirmation: true,
      manual_confirmation_fields: PORTFOLIO_SCREENSHOT_FIELDS,
    },
    dashboardContract: {
      requiredFinalDataFields: ['portfolio', 'holdings', 'assets', 'comparison', 'imageExtraction'],
      evidenceFiles: ['evidence/image_extraction.json', 'evidence/data_quality.json', 'evidence/sources.json'],
    },
  };
}

export function buildQuantPilotMcpServers(projectPath: string): Record<string, unknown> {
  const absoluteProjectPath = path.resolve(projectPath);
  const token = process.env.MINIMAX_API_KEY?.trim() || process.env.ANTHROPIC_AUTH_TOKEN?.trim();
  const minimaxMcpEnabled = process.env.QUANTPILOT_ENABLE_MINIMAX_MCP !== '0' && Boolean(token);
  const minimaxBasePath = path.join(absoluteProjectPath, '.quantpilot', 'minimax-mcp');

  const servers: Record<string, unknown> = {
    QuantPilotImage: createSdkMcpServer({
      name: 'QuantPilotImage',
      version: '0.1.0',
      alwaysLoad: true,
      instructions:
        'QuantPilot 图片附件提取工具。用于读取 .quantpilot/attachments.json，确认上传图片文件，并输出持仓截图提取契约。视觉 OCR 不可用时必须标记缺失字段，不得编造。',
      tools: [
        tool(
          'quant_extract_uploaded_image',
          '读取 QuantPilot 上传图片附件清单，校验图片文件并返回持仓截图提取契约。',
          {
            attachmentContextPath: z
              .string()
              .optional()
              .describe('附件清单路径，默认 .quantpilot/attachments.json'),
            imagePath: z
              .string()
              .optional()
              .describe('可选，仅处理指定图片路径；必须位于当前生成项目内'),
            prompt: z.string().optional().describe('用户希望从图片中提取的信息'),
          },
          async (args) => {
            const contextPath = args.attachmentContextPath ?? '.quantpilot/attachments.json';
            const context = await readAttachmentContext(absoluteProjectPath, contextPath);
            const attachments = args.imagePath
              ? [{ id: 'image-1', name: path.basename(args.imagePath), absolutePath: args.imagePath }]
              : context.attachments;

            if (attachments.length === 0) {
              const payload = {
                schemaVersion: 1,
                tool: 'quant-image-extraction',
                status: 'no_attachments',
                message: '未找到上传图片附件，请确认 .quantpilot/attachments.json 是否存在且包含 attachments。',
              };
              return {
                content: [{ type: 'text', text: JSON.stringify(payload, null, 2) }],
              };
            }

            const inspectedImages = [];
            for (let index = 0; index < attachments.length; index += 1) {
              inspectedImages.push(await inspectImage(absoluteProjectPath, attachments[index], index));
            }

            const payload = buildExtractionPayload({
              projectPath: absoluteProjectPath,
              contextPath: context.contextPath,
              prompt: args.prompt,
              inspectedImages,
            });

            return {
              content: [{ type: 'text', text: JSON.stringify(payload, null, 2) }],
            };
          },
          { alwaysLoad: true }
        ),
      ],
    }),
  };

  if (minimaxMcpEnabled) {
    servers.MiniMax = {
      type: 'stdio',
      command: process.env.MINIMAX_MCP_COMMAND?.trim() || 'uvx',
      args: (process.env.MINIMAX_MCP_ARGS?.trim()
        ? process.env.MINIMAX_MCP_ARGS.trim().split(/\s+/)
        : ['minimax-coding-plan-mcp', '-y']),
      env: {
        MINIMAX_API_KEY: token,
        MINIMAX_MCP_BASE_PATH: process.env.MINIMAX_MCP_BASE_PATH?.trim() || minimaxBasePath,
        MINIMAX_API_HOST:
          process.env.MINIMAX_API_HOST?.trim() ||
          process.env.MINIMAX_API_BASE_URL?.trim() ||
          'https://api.minimaxi.com',
        MINIMAX_API_RESOURCE_MODE: process.env.MINIMAX_API_RESOURCE_MODE?.trim() || 'local',
      },
      timeout: Number(process.env.MINIMAX_MCP_TIMEOUT_MS || 120000),
      alwaysLoad: false,
    };
  }

  return servers;
}
