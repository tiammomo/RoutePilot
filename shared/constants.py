"""Shared constants - 从配置文件读取端口配置."""

import os
import sys

# 获取项目根目录
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 添加项目根目录到 Python 路径
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 尝试导入配置（失败时使用默认值）
try:
    from config import server_config

    # Web - 从配置文件读取
    WEB_PORT = server_config.web_port
    WEB_HOST = server_config.web_host

    # Frontend - 从配置文件读取
    NEXTJS_PORT = server_config.frontend_port

except ImportError:
    # 配置加载失败时使用默认值
    WEB_PORT = 38000
    WEB_HOST = "0.0.0.0"
    NEXTJS_PORT = 33001

# Session
SESSION_MAX_AGE = 86400  # 24 hours
SESSION_CLEANUP_INTERVAL = 3600  # 1 hour

# LLM
DEFAULT_MODEL = "gpt-4o-mini"
MAX_TOKENS = 2000
TEMPERATURE = 0.7

# Agent
MAX_REASONING_STEPS = 10
MAX_REASONING_DEPTH = 5
