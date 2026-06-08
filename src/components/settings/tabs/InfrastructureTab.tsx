"use client";

import { FaDatabase, FaServer } from "react-icons/fa";

interface InfrastructureHealth {
  provider: string;
  databaseUrl: string;
  connected: boolean;
  travelTables: string[];
  docker: {
    available: boolean;
    running: boolean;
    service: { name: string; state: string; status: string; image: string } | null;
    error?: string;
  };
  commands: Record<string, string>;
}

const INFRASTRUCTURE_RECOMMENDATIONS = [
  {
    name: "对象存储",
    stage: "产物规模上来后",
    description: "保存截图、导出文件、大 JSON 和采集日志，数据库只保留索引与摘要。",
  },
  {
    name: "任务队列",
    stage: "多用户并发后",
    description: "承载高德补全、Wiki 构建、路线批量评估等耗时任务。",
  },
  {
    name: "缓存层",
    stage: "性能优化阶段",
    description: "缓存常用 POI、区域选项、路线候选和 UGC 聚合结果。",
  },
];

interface InfrastructureTabProps {
  infrastructure: InfrastructureHealth | null;
  infrastructureError: string | null;
  infrastructureLoading: boolean;
  onRefresh: () => void;
  onCopyCommand: (command: string) => void;
}

function InfrastructureTab({
  infrastructure,
  infrastructureError,
  infrastructureLoading,
  onRefresh,
  onCopyCommand,
}: InfrastructureTabProps) {
  const commands = infrastructure?.commands ?? {
    start: "npm run db:up",
    sync: "npm run prisma:push",
    inspect: "npm run db:doctor",
    psql: "npm run db:psql",
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-medium text-slate-900">基础组件配置</h3>
          <p className="mt-1 text-sm text-slate-600">
            管理北京旅游规划本地开发依赖的 PostgreSQL、旅游数据表和后续基础设施入口。
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={infrastructureLoading}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
        >
          {infrastructureLoading ? "检查中..." : "刷新状态"}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
            <FaDatabase className="text-slate-400" />
            主业务库
          </div>
          <p className="mt-2 text-lg font-semibold text-slate-900">
            {infrastructure?.provider === "postgresql"
              ? "PostgreSQL"
              : infrastructure?.provider ?? "未连接"}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            {infrastructure?.connected ? "Prisma schema 可访问" : "等待连接"}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
            <FaServer className="text-slate-400" />
            旅游数据表
          </div>
          <p className="mt-2 text-lg font-semibold text-slate-900">
            {infrastructure?.travelTables.length ?? 0} 张
          </p>
          <p className="mt-1 text-sm text-slate-600">
            通勤边、Wiki 文档和检索分块
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-medium text-slate-500">Docker 服务</p>
          <p className="mt-2 text-lg font-semibold text-slate-900">
            {infrastructure?.docker.running ? "运行中" : "未运行"}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            {infrastructure?.docker.service?.status ?? "postgres compose 服务"}
          </p>
        </div>
      </div>

      {infrastructureError && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          {infrastructureError}
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h4 className="text-sm font-semibold text-slate-900">连接信息</h4>
        <div className="mt-4 space-y-3">
          <div className="rounded-lg bg-slate-50 p-3">
            <p className="text-xs font-medium text-slate-500">DATABASE_URL</p>
            <p className="mt-1 break-all font-mono text-sm text-slate-700">
              {infrastructure?.databaseUrl || "未配置"}
            </p>
          </div>
          <div className="rounded-lg bg-slate-50 p-3">
            <p className="text-xs font-medium text-slate-500">旅游数据表</p>
            <p className="mt-1 text-sm text-slate-700">
              {infrastructure?.travelTables.length
                ? infrastructure.travelTables.join("、")
                : "尚未初始化"}
            </p>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
        <h4 className="text-sm font-semibold text-slate-900">本地运维命令</h4>
        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          {Object.entries(commands).map(([key, command]) => (
            <div
              key={key}
              className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2"
            >
              <code className="text-sm text-slate-700">{command}</code>
              <button
                type="button"
                onClick={() => onCopyCommand(command)}
                className="rounded-md border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                复制
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h4 className="text-sm font-semibold text-slate-900">推荐组件路线</h4>
        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
          {INFRASTRUCTURE_RECOMMENDATIONS.map((item) => (
            <div key={item.name} className="rounded-lg border border-slate-100 bg-slate-50 p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="font-medium text-slate-900">{item.name}</p>
                <span className="rounded-full bg-white px-2 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200">
                  {item.stage}
                </span>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">{item.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export { InfrastructureTab };
export type { InfrastructureTabProps, InfrastructureHealth };
