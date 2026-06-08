"use client";

function AboutTab() {
  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-cyan-600 text-3xl font-black text-white shadow-lg">
          京
        </div>
        <h3 className="text-2xl font-bold text-slate-900">北京旅游规划</h3>
        <p className="mt-2 font-medium text-slate-600">Version 2.0.0</p>
      </div>

      <div className="space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-6">
        <p className="mx-auto max-w-2xl text-center text-base leading-relaxed text-slate-700">
          北京旅游规划是一个本地智能路线规划系统，基于北京 POI 数据、UGC 评价特征和用户偏好，
          自动生成可执行的多方案路线，并支持按预算、时间、步行、排队和人群角色动态重规划。
        </p>

        <div className="grid grid-cols-2 gap-4 text-center">
          <div className="rounded-xl border border-slate-200/50 bg-white p-3">
            <p className="text-xs font-medium text-slate-700">本地 POI/UGC 数据</p>
          </div>
          <div className="rounded-xl border border-slate-200/50 bg-white p-3">
            <p className="text-xs font-medium text-slate-700">本地路线规划</p>
          </div>
          <div className="rounded-xl border border-slate-200/50 bg-white p-3">
            <p className="text-xs font-medium text-slate-700">动态重规划</p>
          </div>
          <div className="rounded-xl border border-slate-200/50 bg-white p-3">
            <p className="text-xs font-medium text-slate-700">约束验证与证据</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export { AboutTab };
