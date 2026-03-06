# 项目问题分析与修复计划

## 一、已修复问题

### 1. 路由导入错误 ✅
- **问题**: `web/src/routes/__init__.py` 引用已删除的 `chat.py`
- **修复**: 移除 chat_router 导入（已在 main.py 中单独导入）
- **文件**: `web/src/routes/__init__.py`

### 2. 流式输出优化 ✅
- **问题**: 之前流式输出是模拟的
- **修复**: 改用 `LLM.astream()` 实现真正的 token 级别流式输出
- **文件**: `web/src/routes/chat_langchain.py`

---

## 二、待处理问题

### 3. 旧版文件清理（可选）
- **文件**:
  - `web/src/routes/chat_old.py` - 旧版 gRPC 路由
  - `web/src/routes/chat_simple.py` - 简化版路由
- **建议**: 可选择归档到 `legacy/` 目录，或保留作为参考

---

## 三、优化建议

### 4. 测试覆盖
- **建议**: 添加单元测试和集成测试

### 5. 文档补充
- **建议**: 补充 API 使用示例

---

## 四、当前架构

```
前端 (33001) → Web API (38000) → LangChain LLM
                     ↓
              Session 持久化
              (data/sessions/)
```

### 关键文件

| 文件 | 说明 |
|------|------|
| `web/src/routes/chat_langchain.py` | 主聊天 API（LangChain 流式） |
| `web/src/main.py` | FastAPI 应用入口 |
| `agent/src/llm/langchain_adapter.py` | LLM 适配器 |
| `agent/src/tools/travel_tools.py` | 旅游工具 |

---

## 五、验证步骤

```bash
# 1. 安装依赖
install_deps.bat

# 2. 启动服务
python run_api.py

# 3. 测试 API
curl -X POST http://localhost:38000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "推荐一个旅游城市"}'

# 4. 打开前端
cd frontend && npm run dev
```

---

## 六、版本历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-03-06 | v3.0 | LangChain + LangGraph 重构 |
| 2026-03-06 | v3.1 | 修复路由导入，优化的流式输出 |
