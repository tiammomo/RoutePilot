"use client";

import { useState } from "react";
import { Pencil, Search, Trash2 } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/utils";
import type { Project as ProjectSummary } from "@/types/project";

interface TaskDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projects: ProjectSummary[];
  editingProject: ProjectSummary | null;
  onEditProject: (project: ProjectSummary | null) => void;
  onUpdateProject: (projectId: string, name: string) => void;
  onOpenProject: (project: ProjectSummary) => void;
  onDeleteProject: (project: ProjectSummary) => void;
  onSearchChange?: (query: string) => void;
  formatTime: (date: string | null) => string;
  formatCliInfo: (cli?: string, model?: string) => string;
  getCapabilityShortName: (capabilityId?: string | null) => string;
}

function TaskDrawer({
  open,
  onOpenChange,
  projects,
  editingProject,
  onEditProject,
  onUpdateProject,
  onOpenProject,
  onDeleteProject,
  formatTime,
  formatCliInfo,
  getCapabilityShortName,
}: TaskDrawerProps) {
  const [search, setSearch] = useState("");

  const filtered = search.trim()
    ? projects.filter((p) => {
        const kw = search.toLowerCase();
        return [p.name, p.description, p.initialPrompt]
          .filter(Boolean)
          .some((v) => String(v).toLowerCase().includes(kw));
      })
    : projects;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="flex w-full max-w-[420px] flex-col p-0 sm:max-w-[420px]">
        <SheetHeader className="border-b px-4 py-3">
          <div className="flex items-baseline gap-1.5">
            <SheetTitle className="text-base">任务记录</SheetTitle>
            <SheetDescription className="text-xs">({projects.length})</SheetDescription>
          </div>
        </SheetHeader>

        <div className="border-b bg-muted/30 px-4 py-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索对话标题..."
              className="pl-9"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {filtered.length === 0 ? (
            <EmptyState
              title="暂无匹配的任务记录"
              description={search ? "尝试其他关键词" : "创建第一个任务开始使用"}
              className="m-4 border-0"
            />
          ) : (
            filtered.map((project) => {
              const isEditing = editingProject?.id === project.id;
              const title = project.name || project.initialPrompt || "未命名任务";
              const capabilityName = getCapabilityShortName(project.travelCapabilityId);

              return (
                <div
                  key={project.id}
                  className="group relative border-b border-slate-100 px-4 py-3 transition-colors hover:bg-slate-50"
                >
                  {isEditing ? (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        const fd = new FormData(e.currentTarget);
                        const name = String(fd.get("name") || "").trim();
                        if (name) onUpdateProject(project.id, name);
                      }}
                      className="space-y-2"
                    >
                      <input
                        name="name"
                        defaultValue={title}
                        autoFocus
                        className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm font-medium shadow-sm outline-none focus:ring-1 focus:ring-ring"
                        onKeyDown={(e) => {
                          if (e.key === "Escape") onEditProject(null);
                        }}
                      />
                      <div className="flex justify-end gap-2">
                        <Button
                          type="button"
                          onClick={() => onEditProject(null)}
                          size="sm"
                          variant="outline"
                          className="h-8"
                        >
                          取消
                        </Button>
                        <Button type="submit" size="sm" className="h-8">
                          保存
                        </Button>
                      </div>
                    </form>
                  ) : (
                    <div>
                      <button
                        type="button"
                        onClick={() => onOpenProject(project)}
                        className="block w-full min-w-0 text-left"
                      >
                        <p className="truncate text-sm font-semibold text-slate-950">
                          {title}
                        </p>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                          <span>{formatTime(project.lastMessageAt || project.createdAt)}</span>
                          <span>@{project.id.slice(-8)}</span>
                        </div>
                        <p className="mt-1 truncate text-xs text-slate-400">
                          {capabilityName} ·{" "}
                          {formatCliInfo(
                            project.preferredCli ?? undefined,
                            project.selectedModel ?? undefined
                          )}
                        </p>
                      </button>
                      <div className="pointer-events-none absolute right-3 top-3 z-10 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                        <button
                          type="button"
                          onClick={() => onEditProject(project)}
                          className="pointer-events-auto rounded-md p-1.5 text-slate-400 hover:bg-white hover:text-red-500"
                          aria-label="重命名任务"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => onDeleteProject(project)}
                          className="pointer-events-auto rounded-md p-1.5 text-slate-400 hover:bg-white hover:text-red-500"
                          aria-label="删除任务"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

export { TaskDrawer };
export type { TaskDrawerProps };
