# Configuration Reference

## 配置文件

- `config/server_config.yaml`: 服务地址、端口、CORS
- `config/llm_config.yaml`: LLM 模型配置（本地私有）
- `config/llm_config.yaml.example`: LLM 示例模板

## 运行时基线

- Python: `3.14.x`（通过 `uv` 管理）
- 虚拟环境路径: 项目根目录 `.venv`

## server_config 关键项

```yaml
web:
  host: "0.0.0.0"
  port: 38000
frontend:
  port: 33001
```

## 前端环境变量

- `NEXT_PUBLIC_API_BASE`: API 根地址，默认 `http://localhost:38000`
- `NEXT_PUBLIC_APP_NAME`: 应用名称（可选）

## 运行时环境变量

- `SHUAI_WEB_PORT`: `run_api.py` 在启动 uvicorn 时注入
- `CORS_ORIGINS`: 逗号分隔，覆盖默认 CORS 白名单
