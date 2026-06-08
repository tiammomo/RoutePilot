"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface SubNavItem {
  id: string;
  label: string;
  icon: ReactNode;
  disabled?: boolean;
  tooltip?: string;
}

interface SubNavProps {
  items: SubNavItem[];
  activeId: string;
  onChange: (id: string) => void;
  actions?: ReactNode;
  className?: string;
}

function SubNav({ items, activeId, onChange, actions, className }: SubNavProps) {
  return (
    <nav
      className={cn(
        "sticky top-0 z-30 flex items-center gap-2 border-b border-slate-200 bg-white/95 px-4 backdrop-blur lg:px-6",
        className
      )}
    >
      <div className="flex h-11 min-w-0 flex-1 items-center gap-1 overflow-x-auto" role="tablist">
        {items.map((item) => {
          const isActive = item.id === activeId;
          const isDisabled = item.disabled;

          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-disabled={isDisabled}
              disabled={isDisabled}
              title={isDisabled ? item.tooltip : undefined}
              onClick={() => {
                if (!isDisabled) onChange(item.id);
              }}
              className={cn(
                "relative flex h-full shrink-0 items-center gap-2 whitespace-nowrap rounded-t-md px-3 text-sm font-medium transition-colors",
                isActive && !isDisabled
                  ? "text-blue-700"
                  : isDisabled
                    ? "cursor-not-allowed text-slate-300"
                    : "text-slate-500 hover:text-slate-700"
              )}
            >
              <span className={cn("h-4 w-4", isDisabled && "opacity-40")}>{item.icon}</span>
              <span className="whitespace-nowrap">{item.label}</span>
              {isDisabled && item.tooltip && (
                <span className="hidden rounded-full border border-slate-200 bg-slate-50 px-1.5 py-0 text-[10px] text-slate-400 group-hover:inline-block sm:inline-block">
                  {item.tooltip}
                </span>
              )}
              {/* Active indicator */}
              {isActive && !isDisabled && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 rounded-t-full bg-blue-600" />
              )}
            </button>
          );
        })}
      </div>

      {actions && (
        <div className="ml-auto flex shrink-0 items-center gap-2">{actions}</div>
      )}
    </nav>
  );
}

export { SubNav };
export type { SubNavProps, SubNavItem };
