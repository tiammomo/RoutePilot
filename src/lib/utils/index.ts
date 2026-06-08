import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * 生成唯一项目 ID。
 */
export function generateProjectId(): string {
  return `project-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * 校验项目名称。
 */
export function validateProjectName(name: string): boolean {
  // 允许字母、数字、连字符、下划线和空格，长度 1 到 50。
  const regex = /^[a-zA-Z0-9-_ ]{1,50}$/;
  return regex.test(name);
}
