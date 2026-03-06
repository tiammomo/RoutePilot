"""
================================================================================
FastAPI Web 服务器启动脚本 - ShuaiTravelAgent Web API Server
================================================================================

本脚本用于启动旅游规划 Agent 的 Web API 服务。

功能说明:
    - 启动 FastAPI Web 服务器
    - 提供 RESTful API 接口
    - LangGraph Agent 已集成到 Web API 中 (v3.x)

使用场景:
    - 启动 Web API 服务供前端调用
    - 提供聊天、会话管理、城市查询等接口

启动方式:
    python run_api.py

配置说明:
    - 服务配置: config/server_config.yaml (Web 端口)
    - LLM 配置: config/llm_config.yaml (模型配置)

服务地址:
    - API 地址: http://localhost:38000
    - 文档地址: http://localhost:38000/rapidoc
    - 健康检查: http://localhost:38000/api/health

输出示例:
    [*] Starting Web API Server...
        Working directory: d:/.../web

    [INFO] Application startup complete
    [INFO] Uvicorn running on http://0.0.0.0:38000

停止方式:
    Ctrl+C (Windows/Linux)
    Command+. (macOS)

架构说明 (v3.x):
    ┌─────────────────────────────────────────────────────────────┐
    │                     run_api.py                              │
    │  启动 FastAPI 服务器，监听端口由 server_config.yaml 配置     │
    └────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                     web/src/main.py                          │
    │  FastAPI 应用主文件，定义所有 API 路由                        │
    └────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
    ┌─────────────────────────────────────────────────────────────┐
    │               LangGraph Agent (已集成)                       │
    │  v3.x: Agent 逻辑直接集成到 Web API，无需独立服务            │
    └─────────────────────────────────────────────────────────────┘

v3.x 变化:
    - 移除独立 Agent gRPC 服务
    - Agent 逻辑集成到 Web API
    - 无需启动 run_agent.py
    - 只需启动 run_api.py 即可
"""

import sys
import os
import subprocess

# =============================================================================
# 初始化项目路径
# =============================================================================

# 获取项目根目录
project_root = os.path.dirname(os.path.abspath(__file__))

# 添加项目根目录到 Python 路径
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入服务配置
from config import server_config

# Web 应用目录
web_path = os.path.join(project_root, 'web')

# 从配置获取端口
WEB_PORT = server_config.web_port


# =============================================================================
# 主程序入口
# =============================================================================

if __name__ == "__main__":
    """
    程序入口点

    执行流程:
        1. 构建 uvicorn 命令
        2. 设置环境变量
        3. 启动子进程运行 FastAPI

    技术说明:
        使用 subprocess.run() 启动 uvicorn 服务器
        uvicorn 是 ASGI 服务器，用于运行 FastAPI 应用
    """

    # ==========================================================================
    # 1. 构建 uvicorn 启动命令
    # ==========================================================================

    # uvicorn 启动参数说明:
    #     -m uvicorn: 使用 uvicorn ASGI 服务器
    #     src.main:app: FastAPI 应用模块路径
    #         - src.main: src/main.py 模块
    #         - app: main.py 中创建 FastAPI 实例的变量名
    #     --host 0.0.0.0: 监听所有网络接口
    #         - 0.0.0.0 表示接受任意来源的连接
    #         - localhost 或 127.0.0.1 表示仅本地访问
    #     --port: 监听端口（从配置文件读取）
    cmd = [
        sys.executable,           # 当前使用的 Python 解释器路径
        "-m", "uvicorn",          # 以模块方式运行 uvicorn
        "src.main:app",           # FastAPI 应用模块
        "--host", server_config.web_host,  # 绑定地址（从配置读取）
        "--port", str(WEB_PORT),           # 监听端口（从配置读取）
        "--log-config", "src/logging_uvicorn.json"  # 日志配置
    ]

    # ==========================================================================
    # 2. 打印启动信息
    # ==========================================================================

    print("[*] 正在启动 Web API 服务器...")
    print(f"    工作目录: {web_path}")
    print(f"    访问地址: http://localhost:{WEB_PORT}")
    print(f"    API文档:  http://localhost:{WEB_PORT}/rapidoc")
    print(f"    Agent:    LangGraph (已集成)")
    print()

    # ==========================================================================
    # 3. 设置环境变量
    # ==========================================================================

    # 获取当前环境变量
    # os.environ.copy() 返回环境变量的字典副本
    # 避免修改父进程的环境变量
    env = os.environ.copy()

    # 传递配置到环境变量（供子进程使用）
    env['SHUAI_WEB_PORT'] = str(WEB_PORT)

    # ==========================================================================
    # 4. 启动 uvicorn 服务器
    # ==========================================================================

    # subprocess.run() 执行命令
    #     cmd: 命令列表
    #     cwd=web_path: 设置子进程的工作目录
    #     env=env: 设置子进程的环境变量
    #
    # 注意事项:
    #     - 阻塞运行，直到服务器停止
    #     - 子进程会继承父进程的环境变量
    #     - Ctrl+C 会同时终止父进程和子进程
    subprocess.run(cmd, cwd=web_path, env=env)

    """
    备选启动方式（直接在当前进程运行）:

        import uvicorn
        from web.src.main import app

        if __name__ == "__main__":
            uvicorn.run(
                "web.src.main:app",
                host="0.0.0.0",
                port=WEB_PORT,
                reload=False  # 开发环境可设为 True 自动重载
            )

    两种方式的区别:
        - subprocess: 更清晰的进程隔离
        - 直接运行: 调试更方便
    """
