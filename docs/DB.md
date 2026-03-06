# 数据库设计文档

## 概述

本系统当前使用 **文件存储** 方式持久化会话数据，后续可扩展为数据库存储。

---

## 存储方案

### 当前方案：文件存储

| 存储类型 | 文件路径 | 说明 |
|----------|----------|------|
| 会话数据 | `data/sessions/sessions.json` | JSON 格式持久化 |

### 存储实现

```python
# 存储抽象 (web/src/storage/session_storage.py)
SessionStorage (ABC)
├── MemorySessionStorage    # 内存存储（开发/测试用）
└── FileSessionStorage     # 文件存储（当前生产使用）
```

---

## 数据模型

### Session（会话）

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 会话唯一标识 (UUID) |
| `name` | string | 会话名称 |
| `created_at` | string | 创建时间 (ISO 8601) |
| `last_active` | string | 最后活跃时间 (ISO 8601) |
| `message_count` | int | 消息数量 |
| `model_id` | string | 当前使用的模型 ID |
| `messages` | array | 消息列表 |
| `user_preferences` | object | 用户偏好设置 |

### Message（消息）

| 字段 | 类型 | 说明 |
|------|------|------|
| `role` | string | 角色：`user` / `assistant` / `system` |
| `content` | string | 消息内容 |
| `timestamp` | string | 时间戳（可选） |
| `reasoning` | string | AI 推理过程（可选） |

### JSON 示例

```json
{
  "sessions": {
    "550e8400-e29b-41d4-a716-446655440000": {
      "session_id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "云南旅游攻略",
      "created_at": "2024-01-15T10:00:00Z",
      "last_active": "2024-01-15T10:30:00Z",
      "message_count": 5,
      "model_id": "minimax-m2-5",
      "messages": [
        {
          "role": "user",
          "content": "推荐一个适合夏天旅游的城市"
        },
        {
          "role": "assistant",
          "content": "云南丽江是一个非常适合夏天旅游的城市...",
          "reasoning": "[Timestamp: 2024-01-15T10:30:05Z]\n\n分析用户需求..."
        }
      ],
      "user_preferences": {}
    }
  }
}
```

---

## 表结构设计（未来数据库版本）

如需迁移到数据库，可参考以下表结构设计：

### sessions 表

```sql
CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      VARCHAR(64) NOT NULL UNIQUE,
    name            VARCHAR(255) DEFAULT '新会话',
    model_id        VARCHAR(64) DEFAULT 'minimax-m2-5',
    message_count   INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_preferences JSONB DEFAULT '{}',
    INDEX idx_session_id (session_id),
    INDEX idx_last_active (last_active)
);
```

### messages 表

```sql
CREATE TABLE messages (
    id              SERIAL PRIMARY KEY,
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    reasoning       TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_id (session_id),
    INDEX idx_created_at (created_at)
);
```

---

## 配置说明

### 会话过期配置

```python
# 默认配置 (web/src/routes/chat_langchain.py)
SESSION_MAX_AGE_SECONDS = 24 * 60 * 60  # 24 小时
```

### 存储路径配置

```yaml
# config/server_config.yaml
storage:
  session:
    type: "file"  # 或 "memory"
    path: "data/sessions/sessions.json"
    max_age_hours: 24
```

---

## 扩展建议

### 推荐迁移方案

| 阶段 | 方案 | 适用场景 |
|------|------|----------|
| 1 | SQLite | 单机部署，轻量级 |
| 2 | PostgreSQL | 生产环境，高并发 |
| 3 | PostgreSQL + Redis | 分布式部署，缓存会话 |

### 迁移注意事项

1. **数据迁移**：编写脚本将 JSON 数据导入数据库
2. **索引优化**：根据查询模式创建适当索引
3. **事务支持**：利用数据库事务保证数据一致性
4. **备份策略**：制定定期备份计划
