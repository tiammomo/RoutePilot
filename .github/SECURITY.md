# RoutePilot 安全策略

## 支持范围

当前维护范围是默认分支上的 RoutePilot V1：`apps/web`、`/api/v1`、A2A/Runtime V2、RAG、Provider Gateway、PostgreSQL/Redis 平台与离线迁移工具。已移除的产品实现不属于支持或兼容范围。

## 私密报告漏洞

不要在公开 issue、讨论、PR 或日志中提交可利用细节、真实 token、用户数据或数据库地址。请通过仓库维护者提供的私密安全报告渠道发送：

- 受影响版本、组件和部署形态；
- 最小复现步骤或 proof of concept；
- 对机密性、完整性、可用性和跨租户隔离的影响；
- 是否涉及凭据、OIDC、分享访问、RLS、A2A、RAG prompt injection、Provider egress 或供应链；
- 可行的缓解或修复建议。

维护者确认后会协调分级、修复、验证和披露时间。修复发布前请不要公开利用细节。

## 高优先级安全边界

- tenant/owner 授权、PostgreSQL RLS 与跨租户对象引用；
- OIDC Authorization Code + PKCE、JWT 算法/issuer/audience 校验和浏览器 cookie；
- Run/A2A 的幂等、CAS、租约、attempt fencing 与取消传播；
- Artifact/public event 对模型推理、工具原始结果和内部错误的投影边界；
- RAG provenance、外部内容 prompt injection 与知识可见性；
- AMap、embedding、数据库、Redis 和 BFF secret 的服务端隔离；
- 历史数据离线导入、archive manifest 与受限运维输出；
- Python/npm/容器依赖与 CI action 供应链。

## Secret 与本地数据

只提交空值或明显 placeholder 的示例配置。不得提交 `.env`、OIDC client secret、cookie key、Provider key、数据库/Redis 密码、access/refresh token、真实 owner mapping、迁移报告或用户数据。

浏览器代码不得使用 `NEXT_PUBLIC_*` 暴露后端 origin 或任何凭据。发现凭据进入 Git 历史后，应先撤销/轮换，再清理历史；仅删除当前文件不等于修复。

## 仓库安全门禁

统一门禁入口：

```bash
python scripts/v1_quality_gate.py
```

CI 还执行真实 PostgreSQL/Redis 集成测试、依赖审计、gitleaks、Compose/Docker 构建、SBOM 与镜像漏洞扫描。相关配置位于：

- `.github/workflows/v1-quality.yml`
- `.github/dependabot.yml`
- `deploy/security/gitleaks.toml`
- `deploy/security/postgres-v1-init.sh`
- `deploy/security/postgres-v1-grants.sql`

本地或 CI 通过不代表生产安全评审完成。生产仍需平台级 TLS/WAF、secret manager、网络 egress allowlist、PITR/恢复演练、镜像签名验证、集中审计与事件响应。
