# 数据库设计文档

## 概述

本项目当前版本使用**内存存储**作为数据持久化方案，未使用传统数据库。未来版本计划迁移到 SQLite 或 PostgreSQL。

本文档描述当前的数据模型设计，为未来数据库迁移提供参考。

---

## 目录

- [存储方案](#存储方案)
- [数据模型](#数据模型)
- [数据结构](#数据结构)
- [索引设计](#索引设计)
- [存储接口](#存储接口)
- [迁移计划](#迁移计划)

---

## 存储方案

### 当前方案：内存存储

| 特性 | 说明 |
|-----|------|
| 数据位置 | 进程内存 (Python dict) |
| 持久化 | 无（服务重启后数据丢失） |
| 适用场景 | 开发环境、测试、小规模使用 |
| 优点 | 零配置、高性能、无依赖 |
| 缺点 | 数据易丢失、无法多实例共享 |

### 存储位置

```
web/src/repositories/
├── session_repository.py   # 会话仓储
└── city_repository.py      # 城市信息仓储
```

### 数据目录结构

```
data/
└── sessions/               # 会话数据存储目录（未来使用）
    └── .gitkeep
```

---

## 数据模型

### 实体关系图

```
┌─────────────────────────────────────────────────┐
│                   Session (会话)                 │
├─────────────────────────────────────────────────┤
│ - session_id: string (PK)                       │
│ - name: string                                  │
│ - messages: Message[]                           │
│ - message_count: int                            │
│ - model_id: string                              │
│ - created_at: datetime                          │
│ - last_active: datetime                         │
└─────────────────────────────────────────────────┘
                         │
                         │ 1:N
                         ▼
┌─────────────────────────────────────────────────┐
│                   Message (消息)                 │
├─────────────────────────────────────────────────┤
│ - role: string (user/assistant)                 │
│ - content: string                               │
│ - timestamp: datetime                           │
│ - reasoning: string (optional)                  │
└─────────────────────────────────────────────────┘
```

### Session (会话)

会话是用户与 AI 助手进行对话的独立上下文容器。

| 字段 | 类型 | 约束 | 说明 |
|-----|------|-----|------|
| session_id | string | PK, UUID | 会话唯一标识 |
| name | string | - | 会话名称 |
| messages | Message[] | - | 消息历史数组 |
| message_count | int | - | 消息数量 |
| model_id | string | - | 当前使用的模型ID |
| created_at | datetime | - | 创建时间 |
| last_active | datetime | - | 最后活跃时间 |

**示例数据**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "云南旅游攻略",
  "messages": [
    {
      "role": "user",
      "content": "云南有哪些好玩的地方？",
      "timestamp": "2024-01-15T10:00:00Z",
      "reasoning": null
    },
    {
      "role": "assistant",
      "content": "云南是一个多民族聚居的省份，有很多好玩的地方...",
      "timestamp": "2024-01-15T10:00:01Z",
      "reasoning": "[已思考 0.5秒]\n\n分析用户需求..."
    }
  ],
  "message_count": 2,
  "model_id": "minimax-m2-5",
  "created_at": "2024-01-15T10:00:00Z",
  "last_active": "2024-01-15T10:00:01Z"
}
```

### Message (消息)

消息是对话中的单条内容记录。

| 字段 | 类型 | 约束 | 说明 |
|-----|------|-----|------|
| role | string | ENUM(user, assistant) | 角色 |
| content | string | - | 消息内容 |
| timestamp | datetime | - | 发送时间 |
| reasoning | string | NULL | AI 思考过程 |

**示例数据**

```json
{
  "role": "assistant",
  "content": "云南是一个多民族聚居的省份，有很多好玩的地方...",
  "timestamp": "2024-01-15T10:00:01Z",
  "reasoning": "[已思考 0.5秒]\n\n分析用户需求：\n用户询问云南的旅游推荐..."
}
```

### City (城市)

城市基础信息表。

| 字段 | 类型 | 约束 | 说明 |
|-----|------|-----|------|
| city_id | string | PK | 城市唯一标识 |
| name | string | - | 城市名称 |
| region | string | - | 所在地区 |
| description | string | - | 城市描述 |
| highlights | string[] | - | 亮点推荐 |
| best_season | string | - | 最佳旅游季节 |
| avg_cost | string | - | 日均消费 |
| created_at | datetime | - | 创建时间 |

**示例数据**

```json
{
  "city_id": "lijiang",
  "name": "丽江",
  "region": "西南",
  "description": "丽江是一个充满民族风情的古城，拥有世界文化遗产丽江古城。",
  "highlights": ["丽江古城", "玉龙雪山", "束河古镇"],
  "best_season": "春秋两季",
  "avg_cost": "2000-3000元/天",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Attraction (景点)

景点信息表。

| 字段 | 类型 | 约束 | 说明 |
|-----|------|-----|------|
| attraction_id | string | PK | 景点唯一标识 |
| city_id | string | FK | 所属城市 |
| name | string | - | 景点名称 |
| category | string | - | 分类 |
| rating | float | - | 评分 (0-5) |
| address | string | - | 地址 |
| description | string | - | 景点描述 |
| tags | string[] | - | 标签 |

**示例数据**

```json
{
  "attraction_id": "lijiang-ancient-town",
  "city_id": "lijiang",
  "name": "丽江古城",
  "category": "历史文化",
  "rating": 4.8,
  "address": "云南省丽江市古城区",
  "description": "世界文化遗产，纳西族文化中心...",
  "tags": ["历史", "文化", "古城", "摄影"]
}
```

### ModelConfig (模型配置)

LLM 模型配置表。

| 字段 | 类型 | 约束 | 说明 |
|-----|------|-----|------|
| model_id | string | PK | 模型唯一标识 |
| name | string | - | 显示名称 |
| provider | string | - | 提供商 (openai/anthropic/google) |
| model | string | - | 模型名称 |
| api_base | string | - | API 基础URL |
| api_key | string | - | API Key (加密存储) |
| api_version | string | - | API 版本 |
| temperature | float | - | 温度参数 |
| max_tokens | int | - | 最大Token数 |
| timeout | int | - | 超时时间(秒) |
| max_retries | int | - | 最大重试次数 |
| status | string | - | 状态 (available/error/disabled) |

**示例数据**

```json
{
  "model_id": "minimax-m2-5",
  "name": "MiniMax M2.5",
  "provider": "anthropic",
  "model": "MiniMax-M2.5",
  "api_base": "https://api.minimaxi.com/anthropic",
  "api_key": "sk-xxx",
  "temperature": 0.7,
  "max_tokens": 2000,
  "timeout": 60,
  "max_retries": 3,
  "status": "available"
}
```

---

## 数据结构

### TypeScript 类型定义

```typescript
// 前端类型定义 (frontend/src/types/index.ts)

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  reasoning?: string;
}

export interface SessionInfo {
  session_id: string;
  message_count: number;
  last_active: string;
  name?: string;
  model_id?: string;
}

export interface City {
  city_id: string;
  name: string;
  region: string;
  description: string;
  highlights: string[];
  best_season: string;
  avg_cost: string;
}

export interface Attraction {
  attraction_id: string;
  city_id: string;
  name: string;
  category: string;
  rating: number;
  address: string;
  description: string;
  tags: string[];
}

export interface ModelInfo {
  model_id: string;
  name: string;
  provider: string;
  model: string;
}
```

### Python 数据类

```python
# backend data classes

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import uuid

@dataclass
class Message:
    role: str  # 'user' | 'assistant'
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    reasoning: Optional[str] = None

@dataclass
class Session:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "新会话"
    messages: List[Message] = field(default_factory=list)
    message_count: int = 0
    model_id: str = "minimax-m2-5"
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_active: datetime = field(default_factory=datetime.utcnow)

@dataclass
class City:
    city_id: str
    name: str
    region: str
    description: str
    highlights: List[str] = field(default_factory=list)
    best_season: str = ""
    avg_cost: str = ""
```

---

## 索引设计

### 未来数据库索引设计

#### 会话表索引

| 索引名称 | 字段 | 类型 | 说明 |
|---------|------|-----|------|
| PRIMARY | session_id | PRIMARY | 主键索引 |
| idx_session_last_active | last_active | INDEX | 按活跃时间排序 |
| idx_session_created | created_at | INDEX | 按创建时间排序 |

#### 消息表索引

| 索引名称 | 字段 | 类型 | 说明 |
|---------|------|-----|------|
| PRIMARY | id | PRIMARY | 自增主键 |
| fk_message_session | session_id | FOREIGN KEY | 外键索引 |

#### 城市表索引

| 索引名称 | 字段 | 类型 | 说明 |
|---------|------|-----|------|
| PRIMARY | city_id | PRIMARY | 主键索引 |
| idx_city_region | region | INDEX | 按地区查询 |

---

## 存储接口

### SessionRepository 接口

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class SessionRepository(ABC):
    """会话仓储抽象接口"""

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> str:
        """创建会话"""
        pass

    @abstractmethod
    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话"""
        pass

    @abstractmethod
    async def update(self, session_id: str, data: Dict[str, Any]) -> bool:
        """更新会话"""
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """删除会话"""
        pass

    @abstractmethod
    async def list_all(self, include_empty: bool = False) -> List[Dict[str, Any]]:
        """列出所有会话"""
        pass

    @abstractmethod
    async def add_message(self, session_id: str, message: Dict[str, Any]) -> bool:
        """添加消息"""
        pass

    @abstractmethod
    async def clear_messages(self, session_id: str) -> bool:
        """清空消息"""
        pass
```

### CityRepository 接口

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class CityRepository(ABC):
    """城市信息仓储抽象接口"""

    @abstractmethod
    async def list_cities(self, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """列出城市"""
        pass

    @abstractmethod
    async def get_city(self, city_id: str) -> Optional[Dict[str, Any]]:
        """获取城市详情"""
        pass

    @abstractmethod
    async def get_attractions(self, city_id: str) -> List[Dict[str, Any]]:
        """获取城市景点"""
        pass

    @abstractmethod
    async def list_regions(self) -> List[str]:
        """列出地区"""
        pass

    @abstractmethod
    async def list_tags(self) -> List[Dict[str, str]]:
        """列出标签"""
        pass
```

### 内存实现

```python
# web/src/repositories/memory_session_repository.py

class MemorySessionRepository:
    """内存会话仓储实现"""

    def __init__(self):
        self._sessions: Dict[str, Dict] = {}

    async def create(self, data: Dict[str, Any]) -> str:
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            'session_id': session_id,
            'name': data.get('name', '新会话'),
            'messages': [],
            'message_count': 0,
            'model_id': data.get('model_id', 'minimax-m2-5'),
            'created_at': datetime.utcnow().isoformat(),
            'last_active': datetime.utcnow().isoformat(),
        }
        return session_id

    async def get(self, session_id: str) -> Optional[Dict]:
        return self._sessions.get(session_id)

    async def update(self, session_id: str, data: Dict) -> bool:
        if session_id in self._sessions:
            self._sessions[session_id].update(data)
            return True
        return False

    async def delete(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    async def list_all(self, include_empty: bool = False) -> List[Dict]:
        sessions = list(self._sessions.values())
        if not include_empty:
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            sessions = [
                s for s in sessions
                if s['message_count'] > 0 or
                datetime.fromisoformat(s['last_active']) > one_hour_ago
            ]
        return sorted(sessions, key=lambda x: x['last_active'], reverse=True)
```

---

## 迁移计划

### 阶段一：SQLite 迁移

**目标**：实现数据持久化

```sql
-- 创建会话表
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    messages TEXT,  -- JSON 存储
    message_count INTEGER DEFAULT 0,
    model_id TEXT DEFAULT 'minimax-m2-5',
    created_at TEXT,
    last_active TEXT
);

-- 创建索引
CREATE INDEX idx_sessions_last_active ON sessions(last_active DESC);
CREATE INDEX idx_sessions_created ON sessions(created_at DESC);
```

**优点**：
- 单文件存储
- 零配置
- 支持 SQL 查询
- 数据持久化

### 阶段二：PostgreSQL 迁移（可选）

**目标**：生产环境部署

```sql
-- 使用 JSONB 存储消息
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    messages JSONB DEFAULT '[]',
    message_count INTEGER DEFAULT 0,
    model_id VARCHAR(100) DEFAULT 'minimax-m2-5',
    created_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW()
);

-- 创建 GIN 索引支持 JSONB 查询
CREATE INDEX idx_sessions_messages ON sessions USING GIN (messages);

-- 创建部分索引
CREATE INDEX idx_sessions_active ON sessions(last_active DESC)
    WHERE message_count > 0;
```

**优点**：
- 高并发支持
- 完善的事务支持
- 强大的查询能力
- 适合生产环境

### 数据迁移脚本

```python
# scripts/migrate_memory_to_sqlite.py

import sqlite3
import json
from datetime import datetime

def migrate():
    """内存数据迁移到 SQLite"""
    conn = sqlite3.connect('data/sessions.db')
    cursor = conn.cursor()

    # 创建表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            messages TEXT,
            message_count INTEGER DEFAULT 0,
            model_id TEXT DEFAULT 'minimax-m2-5',
            created_at TEXT,
            last_active TEXT
        )
    ''')

    # 从内存读取数据并迁移
    # ... migration logic ...

    conn.commit()
    conn.close()
```

---

## 备份策略

### 当前方案

```bash
# 手动备份会话数据
cp -r data/sessions_backup data/sessions_$(date +%Y%m%d)
```

### 未来方案

```python
# 定时备份脚本
import schedule
import shutil

def backup_database():
    """每日备份数据库"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    shutil.copy('data/sessions.db', f'backups/sessions_{timestamp}.db')

schedule.every().day.at("03:00").do(backup_database)
```

---

## 安全性

### 当前状态

- API Key 明文存储在 YAML 配置文件中
- 无数据加密
- 无访问控制

### 安全措施（未来）

1. **敏感数据加密**
   ```python
   from cryptography.fernet import Fernet

   def encrypt_api_key(key: str) -> str:
       f = Fernet(settings.ENCRYPTION_KEY)
       return f.encrypt(key.encode()).decode()
   ```

2. **访问控制**
   - 添加 JWT 认证中间件
   - 实现用户权限管理

3. **数据隔离**
   - 多租户数据隔离
   - 用户只能访问自己的会话
