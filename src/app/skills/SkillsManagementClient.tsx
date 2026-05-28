"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  CheckCircle2,
  Code2,
  FileText,
  FolderTree,
  History,
  Loader2,
  Search,
  TriangleAlert,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { formatCompactDate as formatTime } from '@/components/quant/console-primitives';
import {
  SourceTree,
  SourceTreeActionMenuOverlay,
  buildSourceTree,
  filterSourceTree,
  formatBytes,
  type SkillDiffData,
  type SkillsPayload,
  type SourceDirectory,
  type SourceFile,
  type SourceState,
  type SourceTreeActionMenu,
  type SourceTreeActionMenuRequest,
} from '@/components/quant/skills-source-tree';
import { SkillsVersionManagerDialog } from '@/components/quant/skills-version-manager-dialog';
import {
  createSkillFolder,
  deleteSkillFile,
  deleteSkillFolder,
  diffSkillVersion,
  fetchSkillsDashboard,
  publishSkillVersion,
  readSkillFile,
  rollbackSkillVersion,
  saveSkillFile,
  uploadSkillPackage,
} from '@/lib/quant/skills-management-api';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import type { SkillHealthStatus } from '@/lib/quant/skills-dashboard';

type ToastState = { type: 'success' | 'error'; message: string } | null;

const statusLabels: Record<SkillHealthStatus, string> = {
  ok: '正常',
  warning: '需同步',
  error: '异常',
};

const statusStyles: Record<SkillHealthStatus, string> = {
  ok: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  warning: 'border-amber-200 bg-amber-50 text-amber-700',
  error: 'border-red-200 bg-red-50 text-red-700',
};

function pillClass(status: SkillHealthStatus) {
  return `inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${statusStyles[status]}`;
}

export default function SkillsManagementClient({ initialData }: { initialData: SkillsPayload }) {
  const [payload, setPayload] = useState<SkillsPayload>(initialData);
  const [selectedId, setSelectedId] = useState<string | null>(initialData.skills[0]?.id ?? null);
  const [isSkillSelectorOpen, setIsSkillSelectorOpen] = useState(false);
  const [isVersionManagerOpen, setIsVersionManagerOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | SkillHealthStatus>('all');
  const [source, setSource] = useState<SourceState | null>(null);
  const [sourceDraft, setSourceDraft] = useState('');
  const [selectedFilePath, setSelectedFilePath] = useState('SKILL.md');
  const [sourceFileQuery, setSourceFileQuery] = useState('');
  const [expandedSourcePaths, setExpandedSourcePaths] = useState<Set<string>>(new Set());
  const [sourceActionMenu, setSourceActionMenu] = useState<SourceTreeActionMenu | null>(null);
  const [isLoadingSource, setIsLoadingSource] = useState(false);
  const [isSavingSource, setIsSavingSource] = useState(false);
  const [deletingFilePath, setDeletingFilePath] = useState<string | null>(null);
  const [creatingFolderBasePath, setCreatingFolderBasePath] = useState<string | null>(null);
  const [deletingFolderPath, setDeletingFolderPath] = useState<string | null>(null);
  const [isPublishing, setIsPublishing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoadingDiff, setIsLoadingDiff] = useState(false);
  const [diffData, setDiffData] = useState<SkillDiffData | null>(null);
  const [rollingBackVersion, setRollingBackVersion] = useState<string | null>(null);
  const [releaseVersion, setReleaseVersion] = useState('');
  const [releaseSummary, setReleaseSummary] = useState('');
  const [releaseChanges, setReleaseChanges] = useState('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isDraggingUpload, setIsDraggingUpload] = useState(false);
  const [toast, setToast] = useState<ToastState>(null);
  const activeSourceRequest = useRef(0);

  const filteredSkills = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return payload.skills.filter((skill) => {
      if (filter !== 'all' && skill.health.status !== filter) return false;
      if (!keyword) return true;
      return [
        skill.id,
        skill.name,
        skill.version,
        skill.status,
        skill.boundary,
        ...skill.inputs,
        ...skill.outputs,
        ...skill.scripts,
        ...skill.legacyAliases,
      ]
        .join(' ')
        .toLowerCase()
        .includes(keyword);
    });
  }, [payload.skills, query, filter]);

  const selectedSkill =
    filteredSkills.find((skill) => skill.id === selectedId) ??
    payload.skills.find((skill) => skill.id === selectedId) ??
    filteredSkills[0] ??
    null;
  const selectedSkillId = selectedSkill?.id ?? null;
  const selectedSkillVersion = selectedSkill?.version ?? '';
  const selectedSkillDirectoryPathsKey = selectedSkill?.source.directories.map((folder) => folder.path).join('\n') ?? '';

  const sourceDirty = Boolean(source && source.skillId === selectedSkillId && sourceDraft !== source.content);
  const sourceTree = useMemo(() => {
    if (!selectedSkill) return [];
    return buildSourceTree(selectedSkill.source.files, selectedSkill.source.directories);
  }, [selectedSkill]);
  const visibleSourceTree = useMemo(
    () => filterSourceTree(sourceTree, sourceFileQuery),
    [sourceTree, sourceFileQuery]
  );

  const showToast = useCallback((nextToast: ToastState) => {
    setToast(nextToast);
    if (nextToast) {
      window.setTimeout(() => setToast(null), 3200);
    }
  }, []);

  async function refreshDashboard() {
    const nextPayload = await fetchSkillsDashboard();
    setPayload(nextPayload);
    return nextPayload;
  }

  const loadSource = useCallback(async (skillId: string, filePath = 'SKILL.md') => {
    const requestId = activeSourceRequest.current + 1;
    activeSourceRequest.current = requestId;
    setIsLoadingSource(true);
    try {
      const nextSource = await readSkillFile(skillId, filePath);
      if (activeSourceRequest.current !== requestId) return;
      setSource(nextSource);
      setSourceDraft(nextSource.content);
      setSelectedFilePath(nextSource.filePath);
    } catch (error) {
      if (activeSourceRequest.current !== requestId) return;
      showToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      if (activeSourceRequest.current === requestId) {
        setIsLoadingSource(false);
      }
    }
  }, [showToast]);

  function selectSourceFile(file: SourceFile) {
    if (!selectedSkill) return;
    if (!file.editable) {
      showToast({ type: 'error', message: '该文件不是可在线编辑的文本文件，可以通过上传压缩包更新。' });
      return;
    }
    if (sourceDirty && !window.confirm('当前文件有未保存修改，确定切换文件吗？')) {
      return;
    }
    setSelectedFilePath(file.path);
    void loadSource(selectedSkill.id, file.path);
  }

  function selectSkill(skillId: string) {
    if (sourceDirty && !window.confirm('当前文件有未保存修改，确定切换 skill 吗？')) {
      return;
    }
    setSelectedId(skillId);
    setIsSkillSelectorOpen(false);
    setSourceActionMenu(null);
  }

  function toggleSourceDirectory(folderPath: string) {
    setExpandedSourcePaths((previous) => {
      const next = new Set(previous);
      if (next.has(folderPath)) {
        next.delete(folderPath);
      } else {
        next.add(folderPath);
      }
      return next;
    });
  }

  function openSourceActionMenu(
    event: React.SyntheticEvent<HTMLButtonElement>,
    menu: SourceTreeActionMenuRequest
  ) {
    event.preventDefault();
    event.stopPropagation();
    const rect = event.currentTarget.getBoundingClientRect();
    setSourceActionMenu({
      ...menu,
      x: rect.right,
      y: rect.bottom,
    } as SourceTreeActionMenu);
  }

  async function saveSource() {
    if (!selectedSkill || !source) return;
    setIsSavingSource(true);
    try {
      const nextSource = await saveSkillFile({
        skillId: selectedSkill.id,
        filePath: source.filePath,
        content: sourceDraft,
      });
      setSource(nextSource);
      setSourceDraft(nextSource.content);
      setDiffData(null);
      await refreshDashboard();
      showToast({ type: 'success', message: '文件已保存，发布版本前请确认变更说明并重新打包。' });
    } catch (error) {
      showToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      setIsSavingSource(false);
    }
  }

  async function createSourceFile(basePath?: string) {
    if (!selectedSkill) return;
    if (sourceDirty && !window.confirm('当前文件有未保存修改，确定先创建新文件吗？')) {
      return;
    }
    const defaultPath = basePath ? `${basePath}/new_file.md` : 'references/provider_notes.md';
    const filePath = window.prompt('输入新文件路径，例如 references/provider_notes.md 或 scripts/new_metric.py', defaultPath)?.trim();
    if (!filePath) return;
    setCreatingFolderBasePath(basePath ?? '__root__');
    try {
      const nextSource = await saveSkillFile({
        skillId: selectedSkill.id,
        filePath,
        content: filePath.endsWith('.py')
          ? '#!/usr/bin/env python3\n'
          : filePath.endsWith('.json')
            ? '{}\n'
            : '',
      });
      setSource(nextSource);
      setSourceDraft(nextSource.content);
      setSelectedFilePath(nextSource.filePath);
      setDiffData(null);
      await refreshDashboard();
      if (basePath) {
        setExpandedSourcePaths((previous) => new Set([...previous, basePath]));
      }
      showToast({ type: 'success', message: '文件已创建，发布版本前请补充变更说明。' });
    } catch (error) {
      showToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      setCreatingFolderBasePath(null);
    }
  }

  async function createSourceFolder(basePath?: string) {
    if (!selectedSkill) return;
    const defaultPath = basePath ? `${basePath}/new-folder` : 'references';
    const folderPath = window.prompt('输入新文件夹路径，例如 references、scripts/helpers 或 assets/icons', defaultPath)?.trim();
    if (!folderPath) return;
    setCreatingFolderBasePath(basePath ?? '__root__');
    try {
      const nextPayload = await createSkillFolder({
        skillId: selectedSkill.id,
        folderPath,
      });
      setPayload(nextPayload);
      setDiffData(null);
      setExpandedSourcePaths((previous) => new Set([...previous, folderPath, ...(basePath ? [basePath] : [])]));
      showToast({ type: 'success', message: '文件夹已创建，可继续创建文件或上传完整压缩包发布新版本。' });
    } catch (error) {
      showToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      setCreatingFolderBasePath(null);
    }
  }

  async function deleteSourceFile(file?: SourceFile) {
    if (!selectedSkill) return;
    const targetFile = file ?? selectedSkill.source.files.find((item) => item.path === source?.filePath);
    if (!targetFile || targetFile.path === 'SKILL.md') return;
    if (!window.confirm(`确定删除 ${targetFile.path} 吗？删除后需要发布新版本才会同步到包。`)) {
      return;
    }
    setDeletingFilePath(targetFile.path);
    try {
      const nextPayload = await deleteSkillFile({
        skillId: selectedSkill.id,
        filePath: targetFile.path,
      });
      setPayload(nextPayload);
      setDiffData(null);
      if (selectedFilePath === targetFile.path) {
        setSelectedFilePath('SKILL.md');
        setSource(null);
        setSourceDraft('');
        await loadSource(selectedSkill.id, 'SKILL.md');
      }
      showToast({ type: 'success', message: '文件已删除，发布版本前请确认变更说明。' });
    } catch (error) {
      showToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      setDeletingFilePath(null);
    }
  }

  async function deleteSourceFolder(folder: SourceDirectory) {
    if (!selectedSkill) return;
    if (!window.confirm(`确定删除文件夹 ${folder.path} 及其中所有文件吗？删除后需要发布新版本才会同步到包。`)) {
      return;
    }
    setDeletingFolderPath(folder.path);
    try {
      const nextPayload = await deleteSkillFolder({
        skillId: selectedSkill.id,
        folderPath: folder.path,
      });
      setPayload(nextPayload);
      setDiffData(null);
      if (selectedFilePath === folder.path || selectedFilePath.startsWith(`${folder.path}/`)) {
        setSelectedFilePath('SKILL.md');
        setSource(null);
        setSourceDraft('');
        await loadSource(selectedSkill.id, 'SKILL.md');
      }
      showToast({ type: 'success', message: '文件夹已删除，发布版本前请确认变更说明。' });
    } catch (error) {
      showToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      setDeletingFolderPath(null);
    }
  }

  async function publishVersion() {
    if (!selectedSkill) return;
    if (!diffData) {
      showToast({ type: 'error', message: '请先生成发布前 Diff，再确认发版。' });
      return;
    }
    const shouldPublish = window.confirm(
      `确认发布 ${selectedSkill.id} v${releaseVersion}？\n\n` +
      `本次变更：新增 ${diffData.totals.added}，修改 ${diffData.totals.modified}，删除 ${diffData.totals.deleted}。`
    );
    if (!shouldPublish) return;
    setIsPublishing(true);
    try {
      const nextPayload = await publishSkillVersion({
        skillId: selectedSkill.id,
        version: releaseVersion,
        summary: releaseSummary,
        changes: releaseChanges,
        status: selectedSkill.status,
      });
      setPayload(nextPayload);
      setReleaseSummary('');
      setReleaseChanges('');
      setDiffData(null);
      setReleaseVersion(nextPayload.skills.find((skill) => skill.id === selectedSkill.id)?.version ?? releaseVersion);
      showToast({ type: 'success', message: '版本已发布，并已重新打包 skill。' });
    } catch (error) {
      showToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      setIsPublishing(false);
    }
  }

  async function loadVersionDiff() {
    if (!selectedSkill) return;
    if (sourceDirty) {
      showToast({ type: 'error', message: '请先保存当前文件，再生成发布前 Diff。' });
      return;
    }
    setIsLoadingDiff(true);
    try {
      const nextDiff = await diffSkillVersion(selectedSkill.id);
      setDiffData(nextDiff);
      showToast({
        type: 'success',
        message: nextDiff.changed ? '发布前 Diff 已生成，请确认后发版。' : '当前源码与上一版一致。',
      });
    } catch (error) {
      showToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      setIsLoadingDiff(false);
    }
  }

  async function rollbackVersion(version: string) {
    if (!selectedSkill) return;
    const shouldRollback = window.confirm(
      `确认将 ${selectedSkill.id} 回退到 v${version}？\n\n当前源码目录会被该版本快照覆盖。`
    );
    if (!shouldRollback) return;
    setRollingBackVersion(version);
    try {
      const nextPayload = await rollbackSkillVersion({
        skillId: selectedSkill.id,
        version,
      });
      setPayload(nextPayload);
      setDiffData(null);
      setReleaseSummary('');
      setReleaseChanges('');
      setReleaseVersion(version);
      await loadSource(selectedSkill.id, 'SKILL.md');
      showToast({ type: 'success', message: `已回退到 v${version}，并重新打包。` });
    } catch (error) {
      showToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      setRollingBackVersion(null);
    }
  }

  function setSelectedUpload(file: File | null) {
    if (!file) return;
    const fileName = file.name.toLowerCase();
    if (!fileName.endsWith('.zip') && !fileName.endsWith('.tgz') && !fileName.endsWith('.tar.gz')) {
      showToast({ type: 'error', message: '仅支持 .zip、.tgz 或 .tar.gz。' });
      return;
    }
    setUploadFile(file);
  }

  function handlePackageDrop(event: React.DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDraggingUpload(false);
    setSelectedUpload(event.dataTransfer.files?.[0] ?? null);
  }

  async function uploadPackage() {
    if (!selectedSkill || !uploadFile) return;
    setIsUploading(true);
    try {
      const nextPayload = await uploadSkillPackage({
        skillId: selectedSkill.id,
        version: releaseVersion,
        summary: releaseSummary,
        changes: releaseChanges,
        status: selectedSkill.status,
        file: uploadFile,
      });
      setPayload(nextPayload);
      setUploadFile(null);
      setDiffData(null);
      setSelectedFilePath('SKILL.md');
      await loadSource(selectedSkill.id, 'SKILL.md');
      showToast({ type: 'success', message: '上传包已作为新版本发布，并已重新打包。' });
    } catch (error) {
      showToast({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    } finally {
      setIsUploading(false);
    }
  }

  function handlePackageDragOver(event: React.DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDraggingUpload(true);
  }

  useEffect(() => {
    if (!selectedSkill && filteredSkills[0]) {
      setSelectedId(filteredSkills[0].id);
    }
  }, [filteredSkills, selectedSkill]);

  useEffect(() => {
    setSourceActionMenu(null);
    if (!selectedSkillId) return;
    activeSourceRequest.current += 1;
    setSource(null);
    setSourceDraft('');
    setSelectedFilePath('SKILL.md');
    setSourceFileQuery('');
    setExpandedSourcePaths(new Set(selectedSkillDirectoryPathsKey ? selectedSkillDirectoryPathsKey.split('\n') : []));
    setIsLoadingSource(false);
    setReleaseVersion(selectedSkillVersion);
    setReleaseSummary('');
    setReleaseChanges('');
    setUploadFile(null);
    setDiffData(null);
    setIsDraggingUpload(false);
    void loadSource(selectedSkillId, 'SKILL.md');
  }, [loadSource, selectedSkillDirectoryPathsKey, selectedSkillId, selectedSkillVersion]);

  useEffect(() => {
    if (!sourceActionMenu) return;
    let canCloseFromScroll = false;
    const timer = window.setTimeout(() => {
      canCloseFromScroll = true;
    }, 250);
    function closeOnScroll() {
      if (!canCloseFromScroll) return;
      setSourceActionMenu(null);
    }
    function closeNow() {
      setSourceActionMenu(null);
    }
    window.addEventListener('scroll', closeOnScroll, true);
    window.addEventListener('resize', closeNow);
    window.addEventListener('keydown', closeNow);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('scroll', closeOnScroll, true);
      window.removeEventListener('resize', closeNow);
      window.removeEventListener('keydown', closeNow);
    };
  }, [sourceActionMenu]);

  useEffect(() => {
    if (isSkillSelectorOpen || isVersionManagerOpen) {
      setSourceActionMenu(null);
    }
  }, [isSkillSelectorOpen, isVersionManagerOpen]);

  useEffect(() => {
    if (!selectedSkill) return;
    setExpandedSourcePaths((previous) => {
      const next = new Set(previous);
      selectedSkill.source.directories.forEach((folder) => {
        if (sourceFileQuery.trim() || selectedFilePath.startsWith(`${folder.path}/`)) {
          next.add(folder.path);
        }
      });
      return next;
    });
  }, [selectedSkill, selectedFilePath, sourceFileQuery]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 md:px-6">
        <Card className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <Link href="/" className="mb-3 inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-primary">
              <ArrowLeft className="h-4 w-4" />
              返回首页
            </Link>
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-md bg-primary text-lg font-bold text-primary-foreground">
                Q
              </div>
              <div>
                <h1 className="text-2xl font-bold tracking-normal">Skills 管理</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  统一查看核心 skill 的版本、变更记录、压缩包和锁文件状态。
                </p>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center sm:min-w-[360px]">
            <div className="rounded-md border bg-muted/40 px-3 py-2">
              <div className="text-xl font-bold">{payload.totals.total}</div>
              <div className="text-xs text-muted-foreground">核心技能</div>
            </div>
            <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2">
              <div className="text-xl font-bold text-emerald-700">{payload.totals.ok}</div>
              <div className="text-xs text-emerald-700">正常</div>
            </div>
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
              <div className="text-xl font-bold text-amber-700">{payload.totals.warning + payload.totals.error}</div>
              <div className="text-xs text-amber-700">待处理</div>
            </div>
          </div>
        </Card>

        <Sheet open={isSkillSelectorOpen} onOpenChange={setIsSkillSelectorOpen}>
          <SheetContent side="left" className="flex w-[440px] max-w-[92vw] flex-col p-0 sm:max-w-[520px]">
            <SheetHeader className="border-b px-5 py-4">
              <SheetTitle>选择 Skill</SheetTitle>
              <SheetDescription>搜索并切换到需要维护的能力包。</SheetDescription>
            </SheetHeader>
            <div className="border-b p-4">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索 skill、脚本或输出..."
                  className="pl-9"
                />
              </div>
              <div className="mt-3 grid grid-cols-4 gap-1.5">
                {(['all', 'ok', 'warning', 'error'] as const).map((item) => (
                  <Button
                    key={item}
                    type="button"
                    onClick={() => setFilter(item)}
                    size="sm"
                    variant={filter === item ? 'default' : 'secondary'}
                    className="h-8 px-2"
                  >
                    {item === 'all' ? '全部' : statusLabels[item]}
                  </Button>
                ))}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-2">
              {filteredSkills.map((skill) => {
                const active = selectedSkill?.id === skill.id;
                return (
                  <button
                    key={skill.id}
                    type="button"
                    onClick={() => selectSkill(skill.id)}
                    className={`mb-1 w-full rounded-lg border p-3 text-left transition-colors ${
                      active
                        ? 'border-primary/20 bg-primary/10'
                        : 'border-transparent hover:border-border hover:bg-muted/50'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-bold">{skill.name}</div>
                        <div className="mt-1 truncate font-mono text-xs text-muted-foreground">{skill.id}</div>
                      </div>
                      <span className={pillClass(skill.health.status)}>{statusLabels[skill.health.status]}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <span>v{skill.version}</span>
                      <span>•</span>
                      <span>{skill.changelog.releaseCount} 个版本</span>
                      <span>•</span>
                      <span>{skill.source.fileCount} 文件</span>
                      <span>•</span>
                      <span>{skill.source.directoryCount} 目录</span>
                    </div>
                  </button>
                );
              })}
              {filteredSkills.length === 0 && (
                <EmptyState title="没有匹配的 skill" description="尝试其他关键词或筛选条件" className="mx-4 border-0" />
              )}
            </div>
          </SheetContent>
        </Sheet>

        <div className="space-y-5">
          {selectedSkill ? (
            <main className="space-y-5">
              <section className="rounded-lg border border-gray-200 bg-white p-5">
                <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-xl font-bold tracking-normal text-gray-950">{selectedSkill.name}</h2>
                      <span className={pillClass(selectedSkill.health.status)}>
                        {selectedSkill.health.status === 'ok' ? <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> : <TriangleAlert className="mr-1 h-3.5 w-3.5" />}
                        {statusLabels[selectedSkill.health.status]}
                      </span>
                      <span className="rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs font-semibold text-gray-600">
                        v{selectedSkill.version}
                      </span>
                    </div>
                    <p className="mt-3 max-w-3xl text-sm leading-6 text-gray-600">{selectedSkill.boundary}</p>
                  </div>
                  <div className="flex flex-col gap-3 md:min-w-[220px] md:items-end">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setIsSkillSelectorOpen(true)}
                      className="w-full"
                    >
                      <Search className="h-4 w-4" />
                      切换 Skill
                    </Button>
                    <Button
                      type="button"
                      onClick={() => setIsVersionManagerOpen(true)}
                      className="w-full"
                    >
                      <History className="h-4 w-4" />
                      版本管理
                    </Button>
                  </div>
                </div>

                {selectedSkill.health.missing.length > 0 && (
                  <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                    需要处理：{selectedSkill.health.missing.join('、')}。通常运行 `npm run package:skills -- {selectedSkill.id}` 后再执行 `npm run check:skills`。
                  </div>
                )}
              </section>

              <section>
                <Card className="min-w-0 p-4 sm:p-5">
                  <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div className="flex min-w-0 items-center gap-2">
                      <Code2 className="h-4 w-4 text-muted-foreground" />
                      <div className="min-w-0">
                        <h2 className="text-base font-semibold">目录级源码编辑</h2>
                        <p className="truncate text-xs text-muted-foreground">
                          {source?.relativePath ?? `${selectedSkill.source.path}/SKILL.md`}
                        </p>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {sourceDirty && <span className="text-xs text-amber-600">有未保存修改</span>}
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => loadSource(selectedSkill.id, selectedFilePath)}
                        disabled={isLoadingSource}
                      >
                        {isLoadingSource ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                        重新读取
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        onClick={saveSource}
                        disabled={isSavingSource || isLoadingSource || !sourceDirty}
                      >
                        {isSavingSource ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                        保存源码
                      </Button>
                    </div>
                  </div>
                  <div className="grid min-w-0 gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
                    <div className="min-w-0 rounded-md border bg-muted/20">
                      <div className="flex items-center justify-between border-b px-3 py-2">
                        <div className="flex items-center gap-2 text-sm font-semibold">
                          <FolderTree className="h-4 w-4 text-muted-foreground" />
                          文件清单
                        </div>
                        <Badge variant="outline" className="font-normal">
                          {selectedSkill.source.fileCount} 个
                        </Badge>
                      </div>
                      <div className="max-h-[520px] overflow-y-auto p-2">
                        <div className="mb-2 flex gap-2">
                          <div className="relative min-w-0 flex-1">
                            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                            <Input
                              value={sourceFileQuery}
                              onChange={(event) => setSourceFileQuery(event.target.value)}
                              placeholder="搜索文件..."
                              className="h-9 pl-10 pr-3 text-sm"
                            />
                          </div>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => setExpandedSourcePaths(new Set(selectedSkill.source.directories.map((folder) => folder.path)))}
                            className="h-8 px-2"
                          >
                            展开
                          </Button>
                        </div>
                        <SourceTree
                          nodes={visibleSourceTree}
                          selectedFilePath={selectedFilePath}
                          expandedPaths={expandedSourcePaths}
                          deletingFolderPath={deletingFolderPath}
                          deletingFilePath={deletingFilePath}
                          creatingFolderBasePath={creatingFolderBasePath}
                          openMenuPath={sourceActionMenu?.type === 'directory' ? sourceActionMenu.node.path : sourceActionMenu?.file.path ?? null}
                          onToggleDirectory={toggleSourceDirectory}
                          onSelectFile={selectSourceFile}
                          onOpenActionMenu={openSourceActionMenu}
                        />
                      </div>
                    </div>
                    <div className="min-w-0">
                      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <span className="min-w-0 break-all font-mono">{source?.filePath ?? selectedFilePath}</span>
                        {source ? <span>• {formatBytes(source.size)}</span> : null}
                        {source?.updatedAt ? <span>• 更新 {formatTime(source.updatedAt)}</span> : null}
                      </div>
                      <Textarea
                        value={sourceDraft}
                        onChange={(event) => setSourceDraft(event.target.value)}
                        spellCheck={false}
                        className="min-h-[520px] min-w-0 resize-y overflow-x-auto font-mono text-xs leading-5"
                        placeholder="选择一个可编辑文件..."
                      />
                    </div>
                  </div>
                </Card>

              </section>
            </main>
          ) : (
            <main className="rounded-lg border border-gray-200 bg-white p-6 text-sm text-gray-400">
              <EmptyState title="请选择一个 skill" description="从左侧列表选择或使用搜索筛选" className="border-0" />
            </main>
          )}
        </div>
      </div>
      <SkillsVersionManagerDialog
        open={isVersionManagerOpen}
        selectedSkill={selectedSkill}
        sourceDirty={sourceDirty}
        releaseVersion={releaseVersion}
        releaseSummary={releaseSummary}
        releaseChanges={releaseChanges}
        uploadFile={uploadFile}
        diffData={diffData}
        isPublishing={isPublishing}
        isUploading={isUploading}
        isLoadingDiff={isLoadingDiff}
        rollingBackVersion={rollingBackVersion}
        isDraggingUpload={isDraggingUpload}
        onClose={() => setIsVersionManagerOpen(false)}
        onVersionChange={setReleaseVersion}
        onSummaryChange={setReleaseSummary}
        onChangesChange={setReleaseChanges}
        onLoadDiff={loadVersionDiff}
        onPublish={publishVersion}
        onRollback={rollbackVersion}
        onUpload={uploadPackage}
        onPackageDrop={handlePackageDrop}
        onPackageDragOver={handlePackageDragOver}
        onPackageDragLeave={() => setIsDraggingUpload(false)}
        onPackageSelect={setSelectedUpload}
      />
      <SourceTreeActionMenuOverlay
        menu={sourceActionMenu}
        deletingFolderPath={deletingFolderPath}
        deletingFilePath={deletingFilePath}
        onClose={() => setSourceActionMenu(null)}
        onSelectFile={selectSourceFile}
        onCreateFile={createSourceFile}
        onCreateFolder={createSourceFolder}
        onDeleteFile={deleteSourceFile}
        onDeleteFolder={deleteSourceFolder}
      />
      {toast && (
        <div
          className={`fixed bottom-5 right-5 z-50 rounded-md border px-4 py-3 text-sm shadow-lg ${
            toast.type === 'success'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
              : 'border-red-200 bg-red-50 text-red-800'
          }`}
        >
          {toast.message}
        </div>
      )}
    </div>
  );
}
