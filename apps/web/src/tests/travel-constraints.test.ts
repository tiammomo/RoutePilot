import { describe, expect, it } from "vitest";

import { buildPlanningRunInput, buildQuestionRunInput } from "@/features/trip-workspace/run-submission";
import {
  buildTripRequest,
  createDefaultTravelConstraintDraft,
  loadTravelConstraintDraft,
  saveTravelConstraintDraft,
  type TravelConstraintDraft,
} from "@/features/trip-workspace/travel-constraints";
import { commandFingerprint } from "@/shared/lib/idempotency";

class MemoryStorage {
  readonly values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

function validDraft(overrides: Partial<TravelConstraintDraft> = {}): TravelConstraintDraft {
  return {
    ...createDefaultTravelConstraintDraft("2026-07-12"),
    destination: "北京",
    ...overrides,
  };
}

describe("V2 travel constraints", () => {
  it("builds a lightweight question Run without requiring planning constraints", () => {
    expect(buildQuestionRunInput("  北京住哪里方便？ ", "北京住宿", "北京")).toEqual({
      command: {
        type: "trip.ask",
        message: "北京住哪里方便？",
        payload: { title: "北京住宿", locale: "zh-CN", destination_hint: "北京" },
      },
      base_artifact_id: null,
      base_artifact_version: null,
    });
  });

  it("provides useful defaults but still requires an explicit destination", () => {
    const draft = createDefaultTravelConstraintDraft("2026-07-12");

    expect(draft).toMatchObject({
      destination: "",
      start_date: "2026-07-19",
      end_date: "2026-07-21",
      adults: "1",
      seniors: "0",
      budget_min: "1000",
      budget_max: "5000",
      currency: "CNY",
    });
    expect(buildTripRequest(draft, "2026-07-12")).toMatchObject({
      ok: false,
      errors: { destination: "请输入目的地" },
    });
  });

  it("normalizes a valid 31-day request into the exact V2 intake payload", () => {
    const result = buildTripRequest(validDraft({
      start_date: "2026-08-01",
      end_date: "2026-08-31",
      adults: "2",
      seniors: "1",
      budget_min: "3000.50",
      budget_max: "12000",
      currency: "usd",
      preferences: "历史文化，慢节奏, 历史文化",
      accessibility_needs: "少走路；无台阶路线",
    }), "2026-07-12");

    expect(result).toEqual({
      ok: true,
      errors: {},
      value: {
        destination: "北京",
        start_date: "2026-08-01",
        end_date: "2026-08-31",
        adults: 2,
        seniors: 1,
        budget_min: "3000.50",
        budget_max: "12000",
        currency: "USD",
        preferences: ["历史文化", "慢节奏"],
        accessibility_needs: ["少走路", "无台阶路线"],
      },
    });
  });

  it("rejects reversed or overlong dates, empty traveler groups, and inverted budgets", () => {
    expect(buildTripRequest(validDraft({
      start_date: "2026-08-01",
      end_date: "2026-09-01",
      adults: "0",
      seniors: "0",
      budget_min: "5000",
      budget_max: "4999",
    }), "2026-07-12")).toMatchObject({
      ok: false,
      errors: {
        end_date: "单次规划最多覆盖 31 天（含首尾）",
        adults: "至少需要 1 位旅行者",
        budget_max: "最高预算不能低于最低预算",
      },
    });

    expect(buildTripRequest(validDraft({
      start_date: "2026-08-10",
      end_date: "2026-08-09",
    }), "2026-07-12")).toMatchObject({
      ok: false,
      errors: { end_date: "返程日期不能早于出发日期" },
    });

    expect(buildTripRequest(validDraft({
      budget_min: "99999999999999999999999999999999",
      budget_max: "99999999999999999999999999999998",
    }), "2026-07-12")).toMatchObject({
      ok: false,
      errors: { budget_max: "最高预算不能低于最低预算" },
    });
  });

  it("persists only allowlisted fields and isolates drafts by Trip ID", () => {
    const storage = new MemoryStorage();
    const draft = validDraft({ destination: "成都", preferences: "川菜" });
    const unsafeDraft = Object.assign({}, draft, {
      api_key: "must-never-be-persisted",
      access_token: "also-forbidden",
    }) as TravelConstraintDraft;

    saveTravelConstraintDraft("trip-one", unsafeDraft, storage);
    saveTravelConstraintDraft("trip-two", validDraft({ destination: "东京" }), storage);

    expect(loadTravelConstraintDraft("trip-one", storage)).toEqual(draft);
    expect(loadTravelConstraintDraft("trip-two", storage)?.destination).toBe("东京");
    expect([...storage.values.values()].join(" ")).not.toContain("must-never-be-persisted");
    expect([...storage.values.values()].join(" ")).not.toContain("also-forbidden");
  });

  it("keeps natural language, title, base version, and structured request in one Run payload", () => {
    const result = buildTripRequest(validDraft({ preferences: "建筑" }), "2026-07-12");
    if (!result.ok) throw new Error("fixture must be valid");

    const input = buildPlanningRunInput("  上午轻松，下午看展  ", " 北京家庭旅行 ", "artifact-4", 4, result.value);

    expect(input).toEqual({
      command: {
        type: "trip.replan",
        message: "上午轻松，下午看展",
        payload: {
          title: "北京家庭旅行",
          patch: {
            dates: { start_date: result.value.start_date, end_date: result.value.end_date },
            budget: {
              min_amount: result.value.budget_min,
              max_amount: result.value.budget_max,
              currency: result.value.currency,
            },
            preferences: { add: [...result.value.preferences], remove: [] },
          },
        },
      },
      base_artifact_id: "artifact-4",
      base_artifact_version: 4,
    });
    expect(commandFingerprint("同一句话", 4, { trip_request: { destination: "北京" } }))
      .not.toBe(commandFingerprint("同一句话", 4, { trip_request: { destination: "上海" } }));
  });
});
