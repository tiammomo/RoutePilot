"""
================================================================================
Pydantic 模型定义模块
================================================================================

提供项目统一的请求/响应模型定义。

模型分类:
    - Chat: 聊天相关模型
    - Session: 会话相关模型
    - Common: 通用模型

使用示例:
    from schemas import ChatRequest, ChatResponse, SessionInfo

    @app.post("/chat/stream")
    async def chat(request: ChatRequest):
        # 使用 Pydantic 模型
        pass

================================================================================
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


# =============================================================================
# 聊天相关模型
# =============================================================================

class ChatMessage(BaseModel):
    """聊天消息"""
    role: Literal["user", "assistant", "system"] = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")
    timestamp: Optional[str] = Field(None, description="时间戳")


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(..., description="用户消息", min_length=1, max_length=10000)
    session_id: Optional[str] = Field(None, description="会话ID，默认自动创建")
    model: Optional[str] = Field(None, description="模型名称，默认使用配置中的模型")
    temperature: Optional[float] = Field(0.7, description="温度参数", ge=0, le=2)
    max_tokens: Optional[int] = Field(2000, description="最大token数", ge=1, le=4096)
    stream: bool = Field(True, description="是否流式响应")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "推荐一个适合冬季旅游的城市",
                "session_id": "abc123",
                "model": "minimax-m2-5",
                "temperature": 0.7,
                "max_tokens": 2000,
                "stream": True
            }
        }


class ToolCall(BaseModel):
    """工具调用信息"""
    name: str = Field(..., description="工具名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    result: Optional[str] = Field(None, description="工具执行结果")


class ChatResponse(BaseModel):
    """聊天响应"""
    success: bool = Field(..., description="是否成功")
    answer: str = Field(..., description="AI 回复内容")
    session_id: str = Field(..., description="会话ID")
    intent: Optional[str] = Field(None, description="识别到的意图")
    tools_used: List[str] = Field(default_factory=list, description="使用的工具列表")
    reasoning: Optional[str] = Field(None, description="推理过程")
    model: Optional[str] = Field(None, description="使用的模型")
    usage: Optional[Dict[str, int]] = Field(None, description="Token使用量")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "answer": "冬季旅游推荐您去云南大理...",
                "session_id": "abc123",
                "intent": "city_recommendation",
                "tools_used": ["search_cities", "get_travel_tips"],
                "model": "minimax-m2-5",
                "usage": {"prompt_tokens": 100, "completion_tokens": 200}
            }
        }


class ChatStreamChunk(BaseModel):
    """聊天流式响应块"""
    type: Literal["chunk", "tool_start", "tool_end", "reasoning", "done", "error"] = Field(
        ..., description="块类型"
    )
    content: Optional[str] = Field(None, description="文本内容")
    tool: Optional[str] = Field(None, description="工具名称")
    tool_result: Optional[str] = Field(None, description="工具执行结果")
    reasoning: Optional[str] = Field(None, description="推理过程")
    answer: Optional[str] = Field(None, description="完整答案（done类型时返回）")
    error: Optional[str] = Field(None, description="错误信息")


# =============================================================================
# 会话相关模型
# =============================================================================

class SessionInfo(BaseModel):
    """会话信息"""
    session_id: str = Field(..., description="会话ID")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="最后更新时间")
    message_count: int = Field(0, description="消息数量")
    title: Optional[str] = Field(None, description="会话标题")


class SessionCreateRequest(BaseModel):
    """创建会话请求"""
    title: Optional[str] = Field(None, description="会话标题")


class SessionUpdateRequest(BaseModel):
    """更新会话请求"""
    title: str = Field(..., description="会话标题")


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: List[SessionInfo] = Field(..., description="会话列表")
    total: int = Field(..., description="总会话数")


class SessionMessagesResponse(BaseModel):
    """会话消息响应"""
    session_id: str = Field(..., description="会话ID")
    messages: List[ChatMessage] = Field(..., description="消息列表")


# =============================================================================
# 模型相关模型
# =============================================================================

class ModelInfo(BaseModel):
    """模型信息"""
    id: str = Field(..., description="模型ID")
    name: str = Field(..., description="模型名称")
    provider: str = Field(..., description="提供商")
    supports_streaming: bool = Field(True, description="是否支持流式")
    supports_function_calling: bool = Field(True, description="是否支持函数调用")
    context_window: Optional[int] = Field(None, description="上下文窗口大小")


class ModelListResponse(BaseModel):
    """模型列表响应"""
    models: List[ModelInfo] = Field(..., description="模型列表")
    default_model: str = Field(..., description="默认模型")


# =============================================================================
# 城市相关模型
# =============================================================================

class CityInfo(BaseModel):
    """城市信息"""
    id: str = Field(..., description="城市ID")
    name: str = Field(..., description="城市名称")
    province: Optional[str] = Field(None, description="省份")
    description: Optional[str] = Field(None, description="城市描述")
    tags: List[str] = Field(default_factory=list, description="标签")
    rating: Optional[float] = Field(None, description="评分")


class AttractionInfo(BaseModel):
    """景点信息"""
    id: str = Field(..., description="景点ID")
    name: str = Field(..., description="景点名称")
    city: str = Field(..., description="所属城市")
    category: str = Field(..., description="景点类别")
    description: Optional[str] = Field(None, description="景点描述")
    rating: Optional[float] = Field(None, description="评分")
    ticket_price: Optional[str] = Field(None, description="门票价格")
    opening_hours: Optional[str] = Field(None, description="开放时间")


# =============================================================================
# 通用响应模型
# =============================================================================

class ErrorDetail(BaseModel):
    """错误详情"""
    code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误消息")
    details: Optional[Dict[str, Any]] = Field(None, description="详细信息")


class ErrorResponse(BaseModel):
    """错误响应"""
    error: ErrorDetail = Field(..., description="错误信息")


class SuccessResponse(BaseModel):
    """通用成功响应"""
    success: bool = Field(True, description="是否成功")
    message: Optional[str] = Field(None, description="成功消息")
    data: Optional[Dict[str, Any]] = Field(None, description="返回数据")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: Literal["healthy", "degraded", "unhealthy"] = Field(..., description="服务状态")
    version: str = Field(..., description="版本号")
    uptime: float = Field(..., description="运行时间（秒）")
    services: Optional[Dict[str, str]] = Field(None, description="依赖服务状态")


# =============================================================================
# 分页模型
# =============================================================================

class PaginationParams(BaseModel):
    """分页参数"""
    page: int = Field(1, description="页码", ge=1)
    page_size: int = Field(20, description="每页数量", ge=1, le=100)


class PaginatedResponse(BaseModel):
    """分页响应"""
    items: List[Any] = Field(..., description="数据项")
    total: int = Field(..., description="总数量")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")
    total_pages: int = Field(..., description="总页数")


__all__ = [
    # Chat models
    "ChatMessage",
    "ChatRequest",
    "ToolCall",
    "ChatResponse",
    "ChatStreamChunk",
    # Session models
    "SessionInfo",
    "SessionCreateRequest",
    "SessionUpdateRequest",
    "SessionListResponse",
    "SessionMessagesResponse",
    # Model models
    "ModelInfo",
    "ModelListResponse",
    # City models
    "CityInfo",
    "AttractionInfo",
    # Common models
    "ErrorDetail",
    "ErrorResponse",
    "SuccessResponse",
    "HealthResponse",
    # Pagination
    "PaginationParams",
    "PaginatedResponse",
]
