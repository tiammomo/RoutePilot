"use client";

import { useEffect, useState, type ChangeEvent } from "react";
import { createPortal } from "react-dom";

import type {
  TravelConstraintDraft,
  TravelConstraintErrors,
} from "@/features/trip-workspace/travel-constraints";

interface TravelConstraintFormProps {
  idPrefix: string;
  draft: TravelConstraintDraft;
  errors: TravelConstraintErrors;
  expanded: boolean;
  ready: boolean;
  confirmed: boolean;
  confirmationError?: string;
  disabled?: boolean;
  onExpandedChange: (expanded: boolean) => void;
  onChange: (field: keyof TravelConstraintDraft, value: string) => void;
  onConfirm: () => boolean;
}

const CURRENCIES = ["CNY", "USD", "EUR", "JPY", "KRW", "THB", "GBP"] as const;
const PRIMARY_FIELDS: (keyof TravelConstraintDraft)[] = ["destination", "start_date", "end_date"];

export function TravelConstraintForm({
  idPrefix,
  draft,
  errors,
  expanded,
  ready,
  confirmed,
  confirmationError,
  disabled,
  onExpandedChange,
  onChange,
  onConfirm,
}: TravelConstraintFormProps) {
  const [step, setStep] = useState<1 | 2>(1);

  useEffect(() => {
    if (!expanded) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onExpandedChange(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [expanded, onExpandedChange]);

  useEffect(() => {
    if (confirmationError && PRIMARY_FIELDS.some((field) => errors[field])) setStep(1);
  }, [confirmationError, errors]);

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
      required?: boolean;
    } = {},
  ) => {
    const id = `${idPrefix}-${field}`;
    const errorId = `${id}-error`;
    return (
      <label className="constraint-field" htmlFor={id}>
        <span>{label}{options.required !== false && <i aria-hidden="true">必填</i>}</span>
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
  const hasDestination = !!draft.destination.trim();
  const summary = hasDestination
    ? `${draft.destination.trim()} · ${draft.start_date || "日期待定"} 至 ${draft.end_date || "待定"} · ${totalTravelers} 人 · ${draft.budget_min}–${draft.budget_max} ${draft.currency}`
    : "设置目的地与出行日期";

  const dialog = expanded && typeof document !== "undefined" ? createPortal(
    <div className="constraint-dialog-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onExpandedChange(false);
    }}>
      <section
        className="constraint-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${idPrefix}-dialog-title`}
      >
        <header className="constraint-dialog-header">
          <div>
            <span className="constraint-dialog-kicker">行程信息 · {step}/2</span>
            <h2 id={`${idPrefix}-dialog-title`}>{step === 1 ? "先确定去哪里、哪天出发" : "再确认人数和预算"}</h2>
            <p>{step === 1 ? "只需要三个基本信息，其他内容稍后再说。" : "这些字段已有常用默认值，按实际情况调整即可。"}</p>
          </div>
          <button type="button" className="constraint-dialog-close" aria-label="关闭行程信息" onClick={() => onExpandedChange(false)}>×</button>
        </header>

        <div className="constraint-progress" aria-label={`行程信息第 ${step} 步，共 2 步`}>
          <span data-active="true" />
          <span data-active={step === 2} />
        </div>

        <div className="constraint-dialog-body">
          {step === 1 ? (
            <div className="constraint-primary-grid">
              {input("destination", "目的地", { maxLength: 100, placeholder: "例如：北京、东京" })}
              {input("start_date", "出发日期", { type: "date" })}
              {input("end_date", "返程日期", { type: "date" })}
            </div>
          ) : (
            <>
              <div className="constraint-decision-grid">
                <fieldset className="constraint-group">
                  <legend>同行人数</legend>
                  <p>至少 1 位旅行者</p>
                  <div className="constraint-paired-fields">
                    {input("adults", "成人", { type: "number", inputMode: "numeric", min: "0", max: "99" })}
                    {input("seniors", "长者", { type: "number", inputMode: "numeric", min: "0", max: "99", required: false })}
                  </div>
                </fieldset>

                <fieldset className="constraint-group">
                  <legend>总预算</legend>
                  <p>按整趟行程估算，可稍后修改</p>
                  <div className="constraint-budget-fields">
                    {input("budget_min", "最低", { inputMode: "decimal", maxLength: 32, placeholder: "1000" })}
                    <span aria-hidden="true">—</span>
                    {input("budget_max", "最高", { inputMode: "decimal", maxLength: 32, placeholder: "5000" })}
                    <label className="constraint-field constraint-currency" htmlFor={`${idPrefix}-currency`}>
                      <span>币种</span>
                      <select
                        id={`${idPrefix}-currency`}
                        name="currency"
                        value={draft.currency}
                        disabled={disabled}
                        aria-invalid={!!errors.currency}
                        onChange={(event) => onChange("currency", event.target.value)}
                      >
                        {CURRENCIES.map((currency) => <option key={currency} value={currency}>{currency}</option>)}
                      </select>
                      {errors.currency && <small className="constraint-error">{errors.currency}</small>}
                    </label>
                  </div>
                </fieldset>
              </div>

              <details className="constraint-optional">
                <summary><span>补充偏好或行动需求</span><small>选填</small></summary>
                <div className="constraint-notes-grid">
                  <label className="constraint-field" htmlFor={`${idPrefix}-preferences`}>
                    <span>旅行偏好<em>用逗号分隔</em></span>
                    <textarea
                      id={`${idPrefix}-preferences`}
                      name="preferences"
                      rows={2}
                      maxLength={5_200}
                      value={draft.preferences}
                      disabled={disabled}
                      placeholder="历史文化，慢节奏，本地美食"
                      aria-invalid={!!errors.preferences}
                      onChange={(event) => onChange("preferences", event.target.value)}
                    />
                    {errors.preferences && <small className="constraint-error">{errors.preferences}</small>}
                  </label>
                  <label className="constraint-field" htmlFor={`${idPrefix}-accessibility`}>
                    <span>行动与无障碍需求<em>用逗号分隔</em></span>
                    <textarea
                      id={`${idPrefix}-accessibility`}
                      name="accessibility_needs"
                      rows={2}
                      maxLength={5_200}
                      value={draft.accessibility_needs}
                      disabled={disabled}
                      placeholder="少走路，无台阶路线"
                      aria-invalid={!!errors.accessibility_needs}
                      onChange={(event) => onChange("accessibility_needs", event.target.value)}
                    />
                    {errors.accessibility_needs && <small className="constraint-error">{errors.accessibility_needs}</small>}
                  </label>
                </div>
              </details>
            </>
          )}
          {confirmationError && <p id={`${idPrefix}-confirmation-error`} className="constraint-confirm-error" role="alert">{confirmationError}</p>}
        </div>

        <footer className="constraint-dialog-footer">
          {step === 1 ? (
            <>
              <button type="button" className="text-button" onClick={() => onExpandedChange(false)}>稍后填写</button>
              <button type="button" className="primary-button" onClick={() => setStep(2)}>继续</button>
            </>
          ) : (
            <>
              <button type="button" className="text-button" onClick={() => setStep(1)}>返回上一步</button>
              <button type="button" className="primary-button" disabled={disabled} onClick={() => onConfirm()}>保存行程信息</button>
            </>
          )}
        </footer>
      </section>
    </div>,
    document.body,
  ) : null;

  return (
    <section className="constraint-editor" aria-label="行程信息">
      <button
        type="button"
        className="constraint-editor-toggle"
        aria-expanded={expanded}
        onClick={() => {
          setStep(1);
          onExpandedChange(true);
        }}
      >
        <span className="constraint-editor-icon" aria-hidden="true">{confirmed || ready ? "✓" : "1"}</span>
        <span><strong>{confirmed ? "行程信息已确认" : ready ? "已根据问题预填，请核对" : "还需要补充行程信息"}</strong><small>{summary}</small></span>
        <span className="constraint-editor-action">{confirmed ? "编辑" : ready ? "核对" : "补充"}<b aria-hidden="true">→</b></span>
      </button>
      {dialog}
    </section>
  );
}
