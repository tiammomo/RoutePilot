import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  buildFrontendChatRuntimeGoldenFixture,
  type ChatStreamGoldenFixture,
  type FrontendChatRuntimeGoldenFixture,
} from '@/components/chat-area/chatRuntimeReplay';

const CURRENT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(CURRENT_DIR, '../../../..');

function loadJsonFixture<T>(...segments: string[]): T {
  const fixturePath = path.join(PROJECT_ROOT, ...segments);
  return JSON.parse(readFileSync(fixturePath, 'utf-8')) as T;
}

describe('chatRuntimeReplay', () => {
  it('preserves structured plan preview validation errors from the stream contract fixture', () => {
    const sourceFixture = loadJsonFixture<ChatStreamGoldenFixture>('tests', 'golden', 'chat_stream_golden_fixture.json');

    const replayFixture = buildFrontendChatRuntimeGoldenFixture(sourceFixture);
    const planPreview = replayFixture.modes.plan.runtime_state.plan_preview;

    expect(planPreview?.validationErrors).toEqual([
      {
        code: 'TOOL_NOT_REGISTERED',
        message: '<text>',
        step_id: 's2',
        tool: 'not_registered_tool',
      },
    ]);
    expect(replayFixture.modes.react.assistant_message?.diagnostics?.planId).toBe('plan-demo');
    expect(replayFixture.modes.direct.assistant_message?.content).toBe('<text><text>');
  });

  it('matches the checked-in frontend chat runtime golden fixture', () => {
    const sourceFixture = loadJsonFixture<ChatStreamGoldenFixture>('tests', 'golden', 'chat_stream_golden_fixture.json');
    const checkedInFixture = loadJsonFixture<FrontendChatRuntimeGoldenFixture>(
      'tests',
      'golden',
      'frontend_chat_runtime_golden_fixture.json'
    );

    expect(buildFrontendChatRuntimeGoldenFixture(sourceFixture)).toEqual(checkedInFixture);
  });
});
