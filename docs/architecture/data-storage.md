# Data Storage

## 当前策略

- 会话数据默认采用文件存储
- 存储实现位于 `web/src/storage/session_storage.py`
- 运行数据位于 `data/`（已被 `.gitignore` 忽略）

## 当前核心实体

- Session: 会话元信息 + 消息列表
- Message: 角色、内容、时间戳等

## 扩展建议

1. 开发环境可继续使用文件存储
2. 生产环境建议迁移 PostgreSQL
3. 高并发下可增加 Redis 做会话缓存
