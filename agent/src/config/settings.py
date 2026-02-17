"""
pydantic Settings 模块 - 应用配置设置

本模块使用pydantic-settings提供类型安全的应用配置管理。
支持环境变量前缀配置，环境变量名自动加上指定前缀。

配置优先级（从高到低）:
1. 环境变量 (SHUAI_TRAVEL_*)
2. .env 文件中的配置
3. 代码中的默认值

使用示例:
    # 方式1: 使用默认值
    settings = Settings()

    # 方式2: 覆盖特定配置
    settings = Settings(agent_name="MyAgent", llm_model="gpt-4")

    # 方式3: 通过环境变量
    # export SHUAI_TRAVEL_LLM_MODEL="gpt-4"
    # export SHUAI_TRAVEL_GRPC_PORT=50051
    settings = Settings()

    # 访问配置
    print(settings.llm_model)
    print(settings.grpc_port)
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    应用设置类

    继承自pydantic_settings.BaseSettings，自动从环境变量加载配置。
    所有配置项都有默认值，可以在环境变量中覆盖。

    环境变量前缀: SHUAI_TRAVEL_

    配置分类:
        - Agent配置: agent_name, agent_max_steps, agent_max_reasoning_depth
        - LLM配置: llm_api_base, llm_api_key, llm_model, llm_temperature, llm_max_tokens
        - 记忆配置: memory_max_working, memory_max_long_term
        - gRPC配置: grpc_host, grpc_port
        - Web配置: web_host, web_port, web_debug

    示例环境变量:
        SHUAI_TRAVEL_AGENT_NAME=TravelAgent
        SHUAI_TRAVEL_LLM_MODEL=gpt-4o-mini
        SHUAI_TRAVEL_GRPC_PORT=50051
        SHUAI_TRAVEL_WEB_PORT=8000
    """

    # ========================================
    # Agent 配置
    # ========================================
    agent_name: str = "TravelAssistantAgent"  # Agent名称
    agent_max_steps: int = 10  # Agent最大执行步数
    agent_max_reasoning_depth: int = 5  # 最大推理深度

    # ========================================
    # LLM 配置
    # ========================================
    llm_api_base: str = ""  # LLM API基础URL
    llm_api_key: str = ""  # LLM API密钥
    llm_model: str = "gpt-4o-mini"  # 默认模型
    llm_temperature: float = 0.7  # 生成温度 (0.0-1.0)
    llm_max_tokens: int = 2000  # 最大输出token数

    # ========================================
    # 记忆配置
    # ========================================
    memory_max_working: int = 10  # 工作记忆最大消息数
    memory_max_long_term: int = 50  # 长期记忆最大存档数

    # ========================================
    # gRPC 服务配置
    # ========================================
    grpc_host: str = "0.0.0.0"  # gRPC服务监听地址
    grpc_port: int = 50051  # gRPC服务监听端口

    # ========================================
    # Web 服务配置
    # ========================================
    web_host: str = "0.0.0.0"  # Web服务监听地址
    web_port: int = 8000  # Web服务监听端口
    web_debug: bool = True  # 是否开启调试模式

    model_config = {"env_prefix": "SHUAI_TRAVEL_"}  # Pydantic v2 配置
