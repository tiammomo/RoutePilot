import { describe, expect, it } from "vitest";

import {
  consumeQuickStartIntent,
  deriveTripTitle,
  detectExplicitDestination,
  saveQuickStartIntent,
} from "@/features/trip-create/quick-start-intent";

class MemoryStorage {
  readonly values = new Map<string, string>();

  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  setItem(key: string, value: string): void { this.values.set(key, value); }
  removeItem(key: string): void { this.values.delete(key); }
}

describe("travel assistant quick start", () => {
  it("derives a readable bounded workspace title from the real question", () => {
    expect(deriveTripTitle("  第一次去京都，住哪里方便？\n")).toBe("第一次去京都，住哪里方便");
    expect(deriveTripTitle("带父母去北京，希望少走路并且每天不要安排太满，最好还能看到古建筑和博物馆"))
      .toBe("带父母去北京，希望少走路并且每天不要安排太满，最好还能看到古建筑和…");
  });

  it("only prefills a destination that appears explicitly in the question", () => {
    expect(detectExplicitDestination("带父母去北京四天")).toBe("北京");
    expect(detectExplicitDestination("想找一个适合带父母慢慢玩的地方")).toBeUndefined();
  });

  it("moves the bounded intent into the workspace exactly once", () => {
    const storage = new MemoryStorage();
    saveQuickStartIntent("trip-1", "带父母去北京 4 天，少走路", storage);

    expect(consumeQuickStartIntent("trip-1", storage)).toEqual({
      prompt: "带父母去北京 4 天，少走路",
      destination: "北京",
    });
    expect(consumeQuickStartIntent("trip-1", storage)).toBeNull();
  });

  it("rejects malformed or forged prefill state", () => {
    const storage = new MemoryStorage();
    storage.setItem("routepilot.quick-start.v1.trip-2", JSON.stringify({
      version: 1,
      prompt: "想找一个安静的地方",
      destination: "巴黎",
    }));

    expect(consumeQuickStartIntent("trip-2", storage)).toEqual({ prompt: "想找一个安静的地方" });
  });
});
