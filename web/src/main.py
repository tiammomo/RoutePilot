"""
================================================================================
ShuaiTravelAgent Web API Server - ShuaiTravelAgent Web API服务器
================================================================================

本模块是Web服务的入口点，使用FastAPI框架构建REST API。
提供聊天、对话管理、模型配置、城市信息等API接口。

功能特点:
- RESTful API设计
- SSE流式响应支持
- CORS跨域支持
- LangChain + LangGraph Agent
- RapiDoc + ReDoc API文档

API端点:
    GET  /                       - API信息
    GET  /api/health             - 健康检查
    POST /api/chat/stream        - SSE流式聊天 (LangChain Agent)
    GET  /api/sessions           - 获取会话列表
    GET  /api/sessions/{id}      - 获取会话详情
    GET  /api/models             - 获取可用模型
    GET  /api/cities             - 获取城市列表

API文档端点:
    GET /docs                    - 文档选择页面
    GET /rapidoc                 - RapiDoc 页面（支持在线测试）
    GET /redoc                   - ReDoc 页面（纯文档展示）
    GET /openapi.json            - OpenAPI JSON 规范

启动方式:
    # 方式1: 使用 run_api.py（推荐，从配置文件读取端口）
    python run_api.py

    # 方式2: 直接运行
    python main.py --host 0.0.0.0 --port 38000 --debug

    # 方式3: 使用uvicorn
    uvicorn main:app --host 0.0.0.0 --port 38000 --reload

配置说明:
    - 服务配置: config/server_config.yaml
    - LLM 配置: config/llm_config.yaml
    - 环境变量: CORS_ORIGINS（覆盖 CORS 配置）

端口配置优先级:
    1. 环境变量 SHUAI_WEB_PORT / SHUAI_GRPC_PORT
    2. config/server_config.yaml
    3. 代码默认值
"""

import os
import sys
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from src.routes import session_router, model_router, city_router, health_router, apidocs_router
# 使用 LangChain 版聊天路由
from src.routes.chat_langchain import router as chat_router
from src.routes.model import set_config_manager


def create_app() -> FastAPI:
    """
    创建并配置FastAPI应用

    初始化所有中间件、配置、服务和路由。

    初始化流程:
        1. 创建FastAPI实例
        2. 配置CORS中间件（从配置文件读取）
        3. 加载配置管理器
        4. 初始化依赖注入容器
        5. 注册路由
        6. 初始化 LangChain Agent
        7. 注册API文档路由

    Returns:
        FastAPI: 配置完成的FastAPI应用实例
    """
    # 检测运行环境（影响API文档访问策略）
    environment = os.getenv("ENVIRONMENT", "dev")

    app = FastAPI(
        title="ShuaiTravelAgent API",
        description="AI Travel Assistant API with SSE streaming support. "
                    "提供基于 LangChain + LangGraph 的智能旅游规划服务，支持SSE流式响应。",
        version="2.0.0",
        # 禁用默认的 Swagger UI，使用自定义的 RapiDoc/ReDoc
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json"  # OpenAPI JSON 端点
    )

    # =========================================================================
    # CORS 中间件配置（从配置文件读取）
    # =========================================================================
    # 优先级：环境变量 > 配置文件 > 默认值
    try:
        # 获取项目根目录并导入配置
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, project_root)
        from config import server_config
        config_cors = server_config.cors_origins
    except ImportError:
        config_cors = []

    # 构建 CORS 来源列表
    env_cors = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []
    default_cors = ["http://localhost:33001", "http://localhost:33001", "http://localhost:38000", "http://localhost:38000"]

    # 合并来源：环境变量优先，然后是配置文件，最后是默认值
    allowed_origins = [c for c in env_cors if c] or config_cors or default_cors

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # =========================================================================
    # 初始化配置管理器
    # =========================================================================
    try:
        # 获取项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(project_root, 'config', 'llm_config.yaml')

        from src.config.config_manager import ConfigManager
        config_manager = ConfigManager(config_path)
        print(f"[*] Config loaded from: {config_path}")

        # 传递配置管理器到路由
        set_config_manager(config_manager)

    except Exception as e:
        print(f"[!] Warning: Could not load config: {e}")

    # =========================================================================
    # 初始化依赖注入容器
    # =========================================================================
    try:
        from src.dependencies.container import get_container
        get_container()
        print("[*] Dependency container initialized")
    except Exception as e:
        print(f"[!] Warning: Could not initialize container: {e}")

    # =========================================================================
    # 注册业务路由
    # =========================================================================
    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(session_router, prefix="/api", tags=["session"])
    app.include_router(chat_router, prefix="/api", tags=["chat"])
    app.include_router(model_router, prefix="/api", tags=["model"])
    app.include_router(city_router, prefix="/api", tags=["city"])

    # =========================================================================
    # 注册 API 文档路由
    # =========================================================================
    app.include_router(apidocs_router)

    # =========================================================================
    # 根端点
    # =========================================================================
    @app.get("/")
    async def root():
        """根端点 - 返回API基本信息"""
        return {
            "name": "ShuaiTravelAgent API",
            "version": "2.0.0",
            "docs": "/docs",
            "rapidoc": "/rapidoc",
            "redoc": "/redoc",
            "openapi": "/openapi.json"
        }

    # =========================================================================
    # OpenAPI 端点（获取 JSON 规范）
    # =========================================================================
    @app.get("/openapi.json", include_in_schema=False)
    async def get_openapi_spec(request: Request):
        """
        获取 OpenAPI JSON 规范

        RapiDoc 通过此端点获取 API 规范。

        Returns:
            JSON: OpenAPI 3.0 规范文档
        """
        openapi_schema = app.openapi()
        # 动态设置服务器URL
        base_url = str(request.base_url).rstrip('/')
        openapi_schema["servers"] = [
            {"url": base_url, "description": "当前服务器"}
        ]
        return JSONResponse(content=openapi_schema)

    return app


# 创建 app 实例
app = create_app()


def main(host: str = "0.0.0.0", port: int = 38000, debug: bool = False):
    """
    启动Web服务器

    Args:
        host: str 监听地址，默认"0.0.0.0"
        port: int 监听端口，默认38000
        debug: bool 是否开启调试模式，默认False
    """
    # 尝试从配置文件读取默认值
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, project_root)
        from config import server_config

        if host == "0.0.0.0":
            host = server_config.web_host
        if port == 38000:
            port = server_config.web_port
    except ImportError:
        pass

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info",
        timeout_keep_alive=30,  # Keep-alive 超时 30 秒
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='ShuaiTravelAgent Web Server')
    parser.add_argument("--host", default="0.0.0.0", help="服务器监听地址")
    parser.add_argument("--port", type=int, default=38000, help="服务器监听端口")
    parser.add_argument("--debug", action="store_true", help="开启调试模式")

    args = parser.parse_args()

    main(args.host, args.port, args.debug)
