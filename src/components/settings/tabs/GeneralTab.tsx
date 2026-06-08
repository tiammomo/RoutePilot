"use client";

interface GeneralTabProps {
  defaultCliName: string;
  isDefaultCliInstalled: boolean;
  defaultModelName: string;
  configuredServiceCount: number;
  installedAgentCount: number;
  totalAgentCount: number;
  onNavigateToAgents: () => void;
  onNavigateToServices: () => void;
}

const GENERATION_POLICIES = [
  {
    title: "生成工作空间",
    description: "首页任务固定使用 Claude Code runtime 与 MiniMax M2.7 创建工作空间，并继承已配置的服务令牌。",
    status: "自动继承",
  },
  {
    title: "评测链路",
    description: "测试用例、评测集和运行记录使用同一套固定模型与服务连接，便于复盘生成质量。",
    status: "统一配置",
  },
  {
    title: "失败修复",
    description: "运维平台负责健康检查、生成链路观测和失败修复，这里只维护全局默认项。",
    status: "运维台处理",
  },
];

function GeneralTab({
  defaultCliName,
  isDefaultCliInstalled,
  defaultModelName,
  configuredServiceCount,
  installedAgentCount,
  totalAgentCount,
  onNavigateToAgents,
  onNavigateToServices,
}: GeneralTabProps) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-medium text-slate-500">固定运行时</p>
          <p className="mt-2 text-lg font-semibold text-slate-900">{defaultCliName || "未配置"}</p>
          <p className="mt-1 text-sm text-slate-600">
            {isDefaultCliInstalled ? "已安装，可用于新任务" : "未检测到安装状态"}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-medium text-slate-500">固定模型</p>
          <p className="mt-2 text-lg font-semibold text-slate-900">{defaultModelName || "未选择模型"}</p>
          <p className="mt-1 text-sm text-slate-600">首页创建任务时始终采用该模型</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-medium text-slate-500">服务令牌</p>
          <p className="mt-2 text-lg font-semibold text-slate-900">{configuredServiceCount}/3 已配置</p>
          <p className="mt-1 text-sm text-slate-600">GitHub、Supabase、Vercel 连接状态</p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-medium text-slate-900">生成链路固定配置</h3>
            <p className="mt-1 text-sm text-slate-600">
              模型与运行时不再提供界面切换；具体工作空间健康与修复在运维平台处理。
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onNavigateToAgents}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
            >
              查看运行时
            </button>
            <button
              type="button"
              onClick={onNavigateToServices}
              className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
            >
              配置服务令牌
            </button>
          </div>
        </div>

        <div className="mt-5 space-y-3">
          {GENERATION_POLICIES.map((policy) => (
            <div
              key={policy.title}
              className="flex items-start justify-between gap-4 rounded-lg border border-slate-100 bg-slate-50 px-4 py-3"
            >
              <div>
                <p className="font-medium text-slate-900">{policy.title}</p>
                <p className="mt-1 text-sm leading-6 text-slate-600">{policy.description}</p>
              </div>
              <span className="shrink-0 rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200">
                {policy.status}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-slate-900">固定运行时状态</span>
          <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200">
            {installedAgentCount}/{totalAgentCount}
          </span>
        </div>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          项目始终使用 Claude Code runtime 与 MiniMax M2.7；界面不提供 CLI 或模型选择入口。
        </p>
      </div>
    </div>
  );
}

export { GeneralTab };
export type { GeneralTabProps };
