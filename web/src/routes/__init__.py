# Routes Package - API 路由模块
#
# 提供所有业务 API 路由和 API 文档路由
#
# 业务路由 (prefix=/api):
#   - session_router: 会话管理接口
#   - model_router: 模型配置接口
#   - city_router: 城市信息接口
#   - health_router: 健康检查接口
#   - chat_router: 在 main.py 中单独导入（使用 LangChain 版）
#
# 文档路由:
#   - apidocs_router: RapiDoc + ReDoc API 文档

from .session import router as session_router
from .model import router as model_router
from .city import router as city_router
from .health import router as health_router
from .apidocs import router as apidocs_router

__all__ = [
    'session_router',
    'model_router',
    'city_router',
    'health_router',
    'apidocs_router'
]
