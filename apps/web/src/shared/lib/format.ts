export function formatDate(value: string, options?: Intl.DateTimeFormatOptions): string {
  try {
    return new Intl.DateTimeFormat("zh-CN", options ?? { month: "short", day: "numeric" }).format(
      new Date(value),
    );
  } catch {
    return value;
  }
}

export function formatMoney(min: string, max: string, currency: string): string {
  const minValue = Number(min);
  const maxValue = Number(max);
  if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) return `${min}–${max} ${currency}`;
  try {
    const formatter = new Intl.NumberFormat("zh-CN", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    });
    return minValue === maxValue
      ? formatter.format(minValue)
      : `${formatter.format(minValue)} – ${formatter.format(maxValue)}`;
  } catch {
    return `${min}–${max} ${currency}`;
  }
}
