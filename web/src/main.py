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
- 依赖注入容器
- gRPC客户端集成
- RapiDoc + ReDoc API文档

API端点:
    GET  /                       - API信息
    GET  /api/health             - 健康检查
    POST /api/chat/stream        - SSE流式聊天
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
    # 方式1: 直接运行
    python main.py --host 0.0.0.0 --port 8000 --debug

    # 方式2: 使用uvicorn
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

    # 方式3: 使用run_api.py
    python run_api.py

环境变量:
    CORS_ORIGINS                 - CORS允许的来源域名（逗号分隔）
"""

import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from src.routes import chat_router, session_router, model_router, city_router, health_router, apidocs_router
from src.routes.model import set_config_manager


def create_app() -> FastAPI:
    """
    创建并配置FastAPI应用

    初始化所有中间件、配置、服务和路由。

    初始化流程:
        1. 创建FastAPI实例
        2. 配置CORS中间件
        3. 加载配置管理器
        4. 初始化依赖注入容器
        5. 注册路由
        6. 初始化gRPC客户端
        7. 注册API文档路由

    Returns:
        FastAPI: 配置完成的FastAPI应用实例
    """
    import os
    # 检测运行环境（影响API文档访问策略）
    environment = os.getenv("ENVIRONMENT", "dev")

    app = FastAPI(
        title="ShuaiTravelAgent API",
        description="AI Travel Assistant API with SSE streaming support. "
                    "提供基于大语言模型的智能旅游规划服务，支持SSE流式响应。",
        version="1.0.0",
        # 禁用默认的 Swagger UI，使用自定义的 RapiDoc/ReDoc
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json"  # OpenAPI JSON 端点
    )

    # =========================================================================
    # CORS 中间件配置
    # =========================================================================
    # 生产环境应该限制为实际的前端域名
    allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:43001,http://127.0.0.1:43001,http://localhost:48081,http://127.0.0.1:48081").split(",")
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

        # 也传递到需要配置的其他路由
        if hasattr(chat_router, 'set_config_manager'):
            chat_router.set_config_manager(config_manager)

    except Exception as e:
        print(f"[!] Warning: Could not load config: {e}")

    # =========================================================================
    # 初始化依赖注入容器
    # =========================================================================
    from src.dependencies.container import get_container
    get_container()
    print("[*] Dependency container initialized")

    # =========================================================================
    # 注册业务路由
    # =========================================================================
    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(session_router, prefix="/api", tags=["session"])
    app.include_router(chat_router, prefix="/api", tags=["chat"])
    app.include_router(model_router, prefix="/api", tags=["model"])
    app.include_router(city_router, prefix="/api", tags=["city"])

    # =========================================================================
    # 初始化 gRPC 客户端
    # =========================================================================
    try:
        from src.routes.chat import init_grpc_stub
        import os
        grpc_host = os.getenv('GRPC_HOST', 'localhost')
        grpc_port = int(os.getenv('GRPC_PORT', '50051'))
        init_grpc_stub(host=grpc_host, port=grpc_port)
        print(f"[*] gRPC client initialized: {grpc_host}:{grpc_port}")
    except Exception as e:
        print(f"[!] Warning: Could not initialize gRPC client: {e}")

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
            "version": "1.0.0",
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


def main(host: str = "0.0.0.0", port: int = 8000, debug: bool = False):
    """
    启动Web服务器

    Args:
        host: str 监听地址，默认"0.0.0.0"
        port: int 监听端口，默认8000
        debug: bool 是否开启调试模式，默认False
    """
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description='ShuaiTravelAgent Web Server')
    parser.add_argument("--host", default="0.0.0.0", help="服务器监听地址")
    parser.add_argument("--port", type=int, default=8000, help="服务器监听端口")
    parser.add_argument("--debug", action="store_true", help="开启调试模式")

    args = parser.parse_args()

    main(args.host, args.port, args.debug)