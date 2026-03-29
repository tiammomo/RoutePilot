import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  buildArtifactDeliveryBundle,
  buildArtifactDeliveryDescriptor,
  buildArtifactDeliveryHtml,
  buildArtifactSharePayload,
} from '@/components/travel-plan-toolkit/shared';

interface FrontendGoldenModeFixture {
  assistant_message?: {
    content?: string;
    diagnostics?: {
      artifact?: Record<string, unknown> | null;
      subagentEvents?: Array<Record<string, unknown>>;
      executionReceipt?: Record<string, unknown> | null;
    } | null;
  } | null;
}

interface FrontendGoldenFixture {
  modes: Record<string, FrontendGoldenModeFixture>;
}

function loadFrontendRuntimeGoldenFixture(): FrontendGoldenFixture {
  const currentFile = fileURLToPath(import.meta.url);
  const fixturePath = path.resolve(currentFile, '../../../../../tests/golden/frontend_chat_runtime_golden_fixture.json');
  return JSON.parse(readFileSync(fixturePath, 'utf-8')) as FrontendGoldenFixture;
}

describe('travel plan delivery replay snapshot', () => {
  const fixture = loadFrontendRuntimeGoldenFixture();

  it.each(Object.entries(fixture.modes))('replays %s mode into stable delivery html', (mode, modeFixture) => {
    const assistantMessage = modeFixture.assistant_message ?? {};
    const diagnostics = assistantMessage.diagnostics ?? {};
    const artifact = diagnostics.artifact ?? null;
    const subagentEvents = diagnostics.subagentEvents ?? [];
    const executionReceipt = diagnostics.executionReceipt ?? null;
    const fallbackContent = assistantMessage.content ?? '';
    const deliveryBundle = buildArtifactDeliveryBundle(artifact as never, subagentEvents as never, {
      executionReceipt: executionReceipt as never,
      fallbackContent,
    });
    const sharePayload = buildArtifactSharePayload(artifact as never, subagentEvents as never, fallbackContent);

    const descriptor = buildArtifactDeliveryDescriptor(artifact as never, subagentEvents as never, {
      fallbackContent,
      fallbackTitle: sharePayload.title,
    });
    const html = buildArtifactDeliveryHtml(artifact as never, subagentEvents as never, {
      fallbackContent,
      fallbackTitle: sharePayload.title,
    });

    expect(sharePayload.htmlContent).toBe(html);
    expect(deliveryBundle.descriptor).toEqual(descriptor);
    expect(deliveryBundle.htmlContent).toBe(html);
    expect(deliveryBundle.share).toEqual({
      title: sharePayload.title,
      content: sharePayload.content,
    });
    expect({
      deliveryBundle,
      descriptor,
      html,
      shareTitle: sharePayload.title,
      shareContent: sharePayload.content,
    }).toMatchSnapshot();
  });
});
