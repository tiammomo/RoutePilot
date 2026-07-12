import type { ChangeEvent } from "react";

import type {
  TravelConstraintDraft,
  TravelConstraintErrors,
} from "@/features/trip-workspace/travel-constraints";

interface TravelConstraintFormProps {
  idPrefix: string;
  draft: TravelConstraintDraft;
  errors: TravelConstraintErrors;
  expanded: boolean;
  confirmed: boolean;
  confirmationError?: string;
  disabled?: boolean;
  onExpandedChange: (expanded: boolean) => void;
  onChange: (field: keyof TravelConstraintDraft, value: string) => void;
  onConfirm: (confirmed: boolean) => void;
}

const CURRENCIES = ["CNY", "USD", "EUR", "JPY", "KRW", "THB", "GBP"] as const;

export function TravelConstraintForm({
  idPrefix,
  draft,
  errors,
  expanded,
  confirmed,
  confirmationError,
  disabled,
  onExpandedChange,
  onChange,
  onConfirm,
}: TravelConstraintFormProps) {
  const input = (
    field: keyof TravelConstraintDraft,
    label: string,
    options: {
      type?: "text" | "date" | "number";
      inputMode?: "text" | "numeric" | "decimal";
      min?: string;
      max?: string;
      maxLength?: number;
      placeholder?: string;
    } = {},
  ) => {
    const id = `${idPrefix}-${field}`;
    const errorId = `${id}-error`;
    return (
      <label className="constraint-field" htmlFor={id}>
        <span>{label}<i aria-hidden="true">必填</i></span>
        <input
          id={id}
          name={field}
          type={options.type ?? "text"}
          inputMode={options.inputMode}
          min={options.min}
          max={options.max}
          maxLength={options.maxLength}
          placeholder={options.placeholder}
          value={draft[field]}
          disabled={disabled}
          aria-invalid={!!errors[field]}
          aria-describedby={errors[field] ? errorId : undefined}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(field, event.target.value)}
        />
        {errors[field] && <small id={errorId} className="constraint-error">{errors[field]}</small>}
      </label>
    );
  };

  const totalTravelers = (Number(draft.adults) || 0) + (Number(draft.seniors) || 0);
  const summary = draft.destination.trim()
    ? `${draft.destination.trim()} · ${draft.start_date || "日期待定"} · ${totalTravelers} 人`
    : "目的地、日期、人数与预算待确认";

  return (
    <section className="constraint-editor" aria-label="旅行约束编辑器">
      <button
        type="button"
        className="constraint-editor-toggle"
        aria-expanded={expanded}
        aria-controls={`${idPrefix}-panel`}
        onClick={() => onExpandedChange(!expanded)}
      >
        <span><strong>第 2 步 · 填写旅行约束</strong><small>{summary}</small></span>
        <span className="constraint-confirmation-state" data-confirmed={confirmed}>
          {confirmed ? "已确认" : "需确认"}<b aria-hidden="true">{expanded ? "−" : "+"}</b>
        </span>
      </button>

      {expanded && (
        <div className="constraint-editor-panel" id={`${idPrefix}-panel`}>
          <p className="constraint-editor-intro">先填写必须准确的旅行信息。Agent 会严格按这些字段规划，不会从自然语言里猜日期、人数或预算。</p>
          <div className="constraint-field-grid">
            {input("destination", "目的地", { maxLength: 100, placeholder: "例如：北京、东京" })}
            {input("start_date", "出发日期", { type: "date" })}
            {input("end_date", "返程日期", { type: "date" })}
            {input("adults", "成人", { type: "number", inputMode: "numeric", min: "0", max: "99" })}
            {input("seniors", "老人", { type: "number", inputMode: "numeric", min: "0", max: "99" })}
            <label className="constraint-field" htmlFor={`${idPrefix}-currency`}>
              <span>币种<i aria-hidden="true">必填</i></span>
              <input
                id={`${idPrefix}-currency`}
                name="currency"
                type="text"
                inputMode="text"
                maxLength={3}
                list={`${idPrefix}-currency-options`}
                value={draft.currency}
                disabled={disabled}
                aria-invalid={!!errors.currency}
                aria-describedby={errors.currency ? `${idPrefix}-currency-error` : undefined}
                onChange={(event) => onChange("currency", event.target.value.toUpperCase())}
              />
              <datalist id={`${idPrefix}-currency-options`}>
                {CURRENCIES.map((currency) => <option key={currency} value={currency} />)}
              </datalist>
              {errors.currency && <small id={`${idPrefix}-currency-error`} className="constraint-error">{errors.currency}</small>}
            </label>
            {input("budget_min", "最低总预算", { inputMode: "decimal", maxLength: 32, placeholder: "1000" })}
            {input("budget_max", "最高总预算", { inputMode: "decimal", maxLength: 32, placeholder: "5000" })}
          </div>

          <div className="constraint-notes-grid">
            <label className="constraint-field" htmlFor={`${idPrefix}-preferences`}>
              <span>旅行偏好<em>选填，用逗号分隔</em></span>
              <textarea
                id={`${idPrefix}-preferences`}
                name="preferences"
                rows={2}
                maxLength={5_200}
                value={draft.preferences}
                disabled={disabled}
                placeholder="历史文化，慢节奏，本地美食"
                aria-invalid={!!errors.preferences}
                aria-describedby={errors.preferences ? `${idPrefix}-preferences-error` : undefined}
                onChange={(event) => onChange("preferences", event.target.value)}
              />
              {errors.preferences && <small id={`${idPrefix}-preferences-error`} className="constraint-error">{errors.preferences}</small>}
            </label>
            <label className="constraint-field" htmlFor={`${idPrefix}-accessibility`}>
              <span>无障碍与行动需求<em>选填，用逗号分隔</em></span>
              <textarea
                id={`${idPrefix}-accessibility`}
                name="accessibility_needs"
                rows={2}
                maxLength={5_200}
                value={draft.accessibility_needs}
                disabled={disabled}
                placeholder="少走路，无台阶路线"
                aria-invalid={!!errors.accessibility_needs}
                aria-describedby={errors.accessibility_needs ? `${idPrefix}-accessibility-error` : undefined}
                onChange={(event) => onChange("accessibility_needs", event.target.value)}
              />
              {errors.accessibility_needs && <small id={`${idPrefix}-accessibility-error`} className="constraint-error">{errors.accessibility_needs}</small>}
            </label>
          </div>

          <label className="constraint-confirm-row" htmlFor={`${idPrefix}-confirmed`}>
            <input
              id={`${idPrefix}-confirmed`}
              type="checkbox"
              checked={confirmed}
              disabled={disabled}
              aria-describedby={confirmationError ? `${idPrefix}-confirmation-error` : undefined}
              onChange={(event) => onConfirm(event.target.checked)}
            />
            <span><strong>我已核对目的地、日期、人数和预算</strong><small>修改任一约束后需要重新确认</small></span>
          </label>
          {confirmationError && <p id={`${idPrefix}-confirmation-error`} className="constraint-confirm-error" role="alert">{confirmationError}</p>}
        </div>
      )}
    </section>
  );
}
