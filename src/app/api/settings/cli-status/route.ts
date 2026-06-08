/**
 * CLI Status API Route
 * GET /api/settings/cli-status - Check CLI installation status
 */

import { NextResponse } from 'next/server';
import { exec } from 'child_process';
import { promisify } from 'util';
import type { CLIStatus } from '@/types/backend';
import { CLAUDE_MODEL_DEFINITIONS } from '@/lib/constants/cliModels';

const execAsync = promisify(exec);

/**
 * Check Claude Code CLI installation
 */
async function checkClaudeCodeCLI(): Promise<{
  installed: boolean;
  version?: string;
  error?: string;
}> {
  try {
    const { stdout } = await execAsync('claude --version');
    const version = stdout.trim();
    return {
      installed: true,
      version,
    };
  } catch (error) {
    return {
      installed: false,
      error: error instanceof Error ? error.message : 'Failed to check CLI',
    };
  }
}

/**
 * GET /api/settings/cli-status
 * Check CLI installation status
 */
export async function GET() {
  try {
    const status: CLIStatus = {
      claude: {
        installed: false,
        checking: false,
      },
    };

    // Check Claude Code CLI installation
    const claudeStatus = await checkClaudeCodeCLI();
    status.claude = {
      installed: claudeStatus.installed,
      version: claudeStatus.version,
      checking: false,
      error: claudeStatus.error,
      models: CLAUDE_MODEL_DEFINITIONS.map((model) => model.id),
    };

    return NextResponse.json(status);
  } catch (error) {
    console.error('[API] Failed to check CLI status:', error);
    return NextResponse.json(
      {
        error: 'Failed to check CLI status',
        message: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
