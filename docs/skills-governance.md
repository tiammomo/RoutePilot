# QuantPilot Skills 统一管理规范

QuantPilot 的 skills 采用“少量核心 skill + legacy alias 兼容 + tgz 包发布”的方式管理。目标是让每个 skill 的能力边界、版本、变更、打包产物和安装结果都可追溯。

## 目录职责

- `.claude/skills.registry.json`：唯一能力注册表，记录核心 skill、版本、边界、输入输出、脚本和验证规则。
- `.claude/skills.changelog.json`：版本变更记录。每次修改核心 skill 的说明、脚本、references 或输出契约，都必须新增对应 release。
- `.claude/skills.lock.json`：打包锁文件，由 `npm run package:skills` 自动生成，记录源目录 hash、压缩包 hash、文件数和版本。
- `.claude/skills/<skill-id>/`：skill 源码目录，包含 `SKILL.md`、可选 `scripts/`、`references/`、`assets/`。
- `.claude/skill-packages/<skill-id>.tgz`：安装到新 workspace 的压缩包产物。

## 核心原则

1. 核心 skill 数量保持克制，新增能力优先并入已有核心 skill。
2. legacy alias 只做兼容，不默认安装；真正能力边界以核心 skill 为准。
3. 修改 skill 必须同步更新版本、changelog、打包产物和 lock。
4. 能用 Python 脚本稳定计算的内容，不要只写成提示词规则。
5. `SKILL.md` 保持短而硬，复杂模板、字段说明和场景矩阵放到 `references/`。

## 版本规则

使用 semver：

- `patch`：只修文案、示例、错别字，不改变输出契约。
- `minor`：新增脚本、references、输出字段、验证规则或场景模板。
- `major`：修改 skill 边界、删除输出字段、移除 legacy 兼容或破坏已有 workspace 假设。

当前阶段多数 skill 未到 1.0，仍按上述语义执行。

## 修改流程

1. 修改 `.claude/skills/<skill-id>/` 下的 `SKILL.md`、`scripts/` 或 `references/`。
2. 更新 `.claude/skills.registry.json` 中该 skill 的 `version`、`boundary`、`outputs`、`scripts` 或 `validation`。
3. 更新 `.claude/skills.changelog.json`，新增同版本 release，写明日期、摘要和变更点。
4. 运行：

```bash
npm run package:skills -- <skill-id>
npm run check:skills
```

5. 如果一次修改多个核心 skill，可运行：

```bash
npm run package:skills
npm run check:skills
```

6. 需要确认平台类型时继续运行：

```bash
npm run type-check
```

## 新增核心 skill 的门槛

只有满足以下任意条件，才新增核心 skill：

- 需要独立脚本或独立数据契约，合并到现有 skill 会明显增加边界混乱。
- 生命周期不同，例如独立的外部数据源治理、独立的实时 gateway、独立的组合优化引擎。
- 验证规则和输入输出与现有核心 skill 完全不同。

否则优先：

- 放到已有 skill 的 `references/`。
- 放到已有 skill 的 `scripts/`。
- 在 `.claude/skills.registry.json` 中扩展该核心 skill 的 `outputs` 或 `validation`。

## 发布检查会挡住什么

`npm run check:skills` 会检查：

- 注册表 schema 和核心 skill 数量上限。
- 核心 skill 是否有 `SKILL.md`。
- 版本号是否符合 semver。
- 每个核心 skill 是否有对应 changelog release。
- 每个核心 skill 是否有 lock entry。
- lock 中的版本、源目录 hash、文件数和 tgz hash 是否与当前文件一致。
- legacy alias 是否指向存在的核心 skill。

如果修改了 skill 但忘记重新打包，会出现 source/package hash mismatch，需要重新运行 `npm run package:skills -- <skill-id>`。

## 当前核心 skill 边界

- `quant-run-planner`：意图澄清、澄清承接、任务规划和 run plan。
- `quant-data-registry`：数据源选择、主备源和降级说明。
- `quant-symbol-resolver`：标的解析。
- `quant-market-data`：实时行情、历史 K 线、指数 ETF、批量行情。
- `quant-fundamentals`：财务、衍生指标、公告和估值情景。
- `quant-indicators`：技术指标、风险、相关性、流动性和趋势模板。
- `quant-backtest`：回测执行和复盘。
- `quant-data-quality`：证据、来源、缺失字段和质量限制。
- `quant-visualization-html`：按场景模板生成可验证金融看板。

## 后续建议

- 增加 `scripts/skill-diff.js`，自动展示两个版本之间的 registry、changelog、source hash 差异。
- 增加 skill 单元测试目录，例如 `.claude/skills/<skill-id>/tests/fixtures`。
- 对有 Python 脚本的 skill 增加 `uv run pytest` 或脚本级 golden fixture 验证。
- 在 GitHub Actions 中加入 `npm run check:skills`、`npm run type-check` 和关键 Python 脚本测试。
