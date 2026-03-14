# Data Storage

## 当前策略

- 会话数据默认采用文件存储
- 存储实现位于 `web/shuai_web/storage/session_storage.py`
- 运行数据位于 `data/`（已被 `.gitignore` 忽略）
- Agent memory 独立持久化到 `data/agent_memory.json`
- Agent memory 已启用原子写入（临时文件 + `os.replace`）并保留 `data/agent_memory.json.bak` 热备

## 当前核心实体

- Session: 会话元信息 + 消息列表
- Message: 角色、内容、时间戳等
- Memory Session: 摘要 + 最近消息 + 用户偏好画像（budget/days/interests 等）

## Agent Memory 持久化细节

1. 写入路径
- 主文件：`data/agent_memory.json`
- 备份：`data/agent_memory.json.bak`

2. 写入流程
- 先写同目录临时文件
- `flush + fsync` 确保内容写入磁盘缓冲
- `os.replace` 原子替换主文件
- 同样流程写入 `.bak`

3. 读取恢复流程
- 先尝试读取主文件
- 主文件损坏时自动回退读取 `.bak`
- 若从 `.bak` 恢复成功，自动回写主文件

4. 目的
- 降低进程中断导致 JSON 半写入损坏的概率
- 提升启动恢复成功率与 memory 可用性

更多细节见：`docs/architecture/agent-memory-mechanisms.md`

## 扩展建议

1. 开发环境可继续使用文件存储
2. 生产环境建议迁移 PostgreSQL
3. 高并发下可增加 Redis 做会话缓存
4. Session 与 Memory 建议统一落同一数据库事务边界，降低双写不一致风险
