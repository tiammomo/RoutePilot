"""Route package exports.

Business routers are mounted under `/api` in `src.main`.
Documentation routers are mounted without API prefix.
"""

from .api_docs import router as api_docs_router
from .city import router as city_router
from .health import router as health_router
from .model import router as model_router
from .session import router as session_router

__all__ = [
    "api_docs_router",
    "city_router",
    "health_router",
    "model_router",
    "session_router",
]
