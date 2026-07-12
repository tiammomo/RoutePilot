import type { TripRequestInput } from "@/shared/api/types";

const STORAGE_PREFIX = "routepilot.trip-constraints.v1.";
const STORAGE_VERSION = 1;
const DECIMAL = /^(0|[1-9][0-9]*)(\.[0-9]{1,4})?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const LIST_SEPARATOR = /[,，;；\n]+/;

export interface TravelConstraintDraft {
  destination: string;
  start_date: string;
  end_date: string;
  adults: string;
  seniors: string;
  budget_min: string;
  budget_max: string;
  currency: string;
  preferences: string;
  accessibility_needs: string;
}

export type TravelConstraintErrors = Partial<Record<keyof TravelConstraintDraft, string>>;

export type TripRequestBuildResult =
  | { ok: true; value: TripRequestInput; errors: TravelConstraintErrors }
  | { ok: false; errors: TravelConstraintErrors };

interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

function addCalendarDays(isoDate: string, days: number): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day + days));
  return date.toISOString().slice(0, 10);
}

export function localToday(now = new Date()): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function createDefaultTravelConstraintDraft(
  today = localToday(),
): TravelConstraintDraft {
  const start = addCalendarDays(today, 7);
  return {
    destination: "",
    start_date: start,
    end_date: addCalendarDays(start, 2),
    adults: "1",
    seniors: "0",
    budget_min: "1000",
    budget_max: "5000",
    currency: "CNY",
    preferences: "",
    accessibility_needs: "",
  };
}

function isRealIsoDate(value: string): boolean {
  if (!ISO_DATE.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.toISOString().slice(0, 10) === value;
}

function dayDifference(start: string, end: string): number {
  const [startYear, startMonth, startDay] = start.split("-").map(Number);
  const [endYear, endMonth, endDay] = end.split("-").map(Number);
  return (
    Date.UTC(endYear, endMonth - 1, endDay) -
    Date.UTC(startYear, startMonth - 1, startDay)
  ) / 86_400_000;
}

function parseTextList(value: string): string[] {
  return [...new Set(value.split(LIST_SEPARATOR).map((item) => item.trim()).filter(Boolean))];
}

function listError(items: string[]): string | undefined {
  if (items.length > 20) return "最多填写 20 项";
  if (items.some((item) => item.length > 256)) return "每一项不能超过 256 个字符";
  return undefined;
}

function validateTraveler(value: string): number | undefined {
  if (!/^\d+$/.test(value)) return undefined;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > 99) return undefined;
  return parsed;
}

function compareDecimal(left: string, right: string): number {
  const [leftInteger, leftFraction = ""] = left.split(".");
  const [rightInteger, rightFraction = ""] = right.split(".");
  if (leftInteger.length !== rightInteger.length) {
    return leftInteger.length > rightInteger.length ? 1 : -1;
  }
  const integerComparison = leftInteger.localeCompare(rightInteger);
  if (integerComparison) return integerComparison;
  return leftFraction.padEnd(4, "0").localeCompare(rightFraction.padEnd(4, "0"));
}

export function buildTripRequest(
  draft: TravelConstraintDraft,
  today = localToday(),
): TripRequestBuildResult {
  const errors: TravelConstraintErrors = {};
  const destination = draft.destination.trim();
  if (!destination) errors.destination = "请输入目的地";
  else if (destination.length > 100) errors.destination = "目的地不能超过 100 个字符";

  const startValid = isRealIsoDate(draft.start_date);
  const endValid = isRealIsoDate(draft.end_date);
  if (!startValid) errors.start_date = "请选择有效的出发日期";
  else if (draft.start_date < today) errors.start_date = "出发日期不能早于今天";
  if (!endValid) errors.end_date = "请选择有效的返程日期";
  if (startValid && endValid) {
    const difference = dayDifference(draft.start_date, draft.end_date);
    if (difference < 0) errors.end_date = "返程日期不能早于出发日期";
    else if (difference > 30) errors.end_date = "单次规划最多覆盖 31 天（含首尾）";
  }

  const adults = validateTraveler(draft.adults);
  const seniors = validateTraveler(draft.seniors);
  if (adults === undefined) errors.adults = "成人数须为 0–99 的整数";
  if (seniors === undefined) errors.seniors = "老人数须为 0–99 的整数";
  if (adults !== undefined && seniors !== undefined && adults + seniors < 1) {
    errors.adults = "至少需要 1 位旅行者";
  }

  const budgetMin = draft.budget_min.trim();
  const budgetMax = draft.budget_max.trim();
  if (budgetMin.length > 32 || !DECIMAL.test(budgetMin)) {
    errors.budget_min = "请输入非负金额，最多保留 4 位小数";
  }
  if (budgetMax.length > 32 || !DECIMAL.test(budgetMax)) {
    errors.budget_max = "请输入非负金额，最多保留 4 位小数";
  }
  if (!errors.budget_min && !errors.budget_max && compareDecimal(budgetMin, budgetMax) > 0) {
    errors.budget_max = "最高预算不能低于最低预算";
  }

  const currency = draft.currency.trim().toUpperCase();
  if (!/^[A-Z]{3}$/.test(currency)) errors.currency = "请选择有效的三位币种代码";

  const preferences = parseTextList(draft.preferences);
  const accessibilityNeeds = parseTextList(draft.accessibility_needs);
  const preferencesError = listError(preferences);
  const accessibilityError = listError(accessibilityNeeds);
  if (preferencesError) errors.preferences = preferencesError;
  if (accessibilityError) errors.accessibility_needs = accessibilityError;

  if (Object.keys(errors).length || adults === undefined || seniors === undefined) {
    return { ok: false, errors };
  }
  return {
    ok: true,
    errors,
    value: {
      destination,
      start_date: draft.start_date,
      end_date: draft.end_date,
      adults,
      seniors,
      budget_min: budgetMin,
      budget_max: budgetMax,
      currency,
      preferences,
      accessibility_needs: accessibilityNeeds,
    },
  };
}

function storageKey(tripId: string): string {
  return `${STORAGE_PREFIX}${encodeURIComponent(tripId)}`;
}

function boundedString(value: unknown, maxLength: number): string | undefined {
  return typeof value === "string" && value.length <= maxLength ? value : undefined;
}

function allowlistedDraft(value: unknown): TravelConstraintDraft | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const source = value as Record<string, unknown>;
  const destination = boundedString(source.destination, 100);
  const startDate = boundedString(source.start_date, 10);
  const endDate = boundedString(source.end_date, 10);
  const adults = boundedString(source.adults, 3);
  const seniors = boundedString(source.seniors, 3);
  const budgetMin = boundedString(source.budget_min, 32);
  const budgetMax = boundedString(source.budget_max, 32);
  const currency = boundedString(source.currency, 3);
  const preferences = boundedString(source.preferences, 5_200);
  const accessibilityNeeds = boundedString(source.accessibility_needs, 5_200);
  if (
    destination === undefined || startDate === undefined || endDate === undefined ||
    adults === undefined || seniors === undefined || budgetMin === undefined ||
    budgetMax === undefined || currency === undefined || preferences === undefined ||
    accessibilityNeeds === undefined
  ) return null;
  return {
    destination,
    start_date: startDate,
    end_date: endDate,
    adults,
    seniors,
    budget_min: budgetMin,
    budget_max: budgetMax,
    currency,
    preferences,
    accessibility_needs: accessibilityNeeds,
  };
}

function browserStorage(): StorageLike | undefined {
  return typeof window === "undefined" ? undefined : window.localStorage;
}

export function loadTravelConstraintDraft(
  tripId: string,
  target: StorageLike | undefined = browserStorage(),
): TravelConstraintDraft | null {
  if (!target) return null;
  try {
    const raw = target.getItem(storageKey(tripId));
    if (!raw || raw.length > 16_000) return null;
    const parsed = JSON.parse(raw) as { version?: unknown; draft?: unknown };
    return parsed.version === STORAGE_VERSION ? allowlistedDraft(parsed.draft) : null;
  } catch {
    return null;
  }
}

export function saveTravelConstraintDraft(
  tripId: string,
  draft: TravelConstraintDraft,
  target: StorageLike | undefined = browserStorage(),
): void {
  if (!target) return;
  const safeDraft = allowlistedDraft(draft);
  if (!safeDraft) return;
  try {
    target.setItem(storageKey(tripId), JSON.stringify({ version: STORAGE_VERSION, draft: safeDraft }));
  } catch {
    // Storage can be unavailable in privacy mode; submission remains functional in memory.
  }
}
