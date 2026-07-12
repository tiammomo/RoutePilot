"""RoutePilot V1 product API, run control plane and trusted A2A mesh."""

from .a2a_routes import router as a2a_router
from .provider_routes import router as provider_router
from .rag_routes import router as rag_router
from .routes import router as v1_router
from .share_routes import router as share_router
from .runtime import V1Runtime, build_default_v1_runtime

v1_router.include_router(a2a_router, tags=["v1-a2a"])
v1_router.include_router(rag_router)
v1_router.include_router(provider_router)
v1_router.include_router(share_router)

__all__ = [
    "V1Runtime",
    "a2a_router",
    "build_default_v1_runtime",
    "provider_router",
    "rag_router",
    "share_router",
    "v1_router",
]
