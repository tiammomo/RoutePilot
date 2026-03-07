"""Start the web API server with uvicorn."""

from __future__ import annotations

import os
import subprocess
import sys

from config import server_config

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_PATH = os.path.join(PROJECT_ROOT, "web")
WEB_PORT = server_config.web_port


if __name__ == "__main__":
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.main:app",
        "--host",
        server_config.web_host,
        "--port",
        str(WEB_PORT),
        "--log-level",
        "info",
    ]

    print("[*] Starting Web API Server...")
    print(f"    Working directory: {WEB_PATH}")
    print(f"    URL: http://localhost:{WEB_PORT}")
    print(f"    API docs: http://localhost:{WEB_PORT}/rapidoc")

    env = os.environ.copy()
    env["SHUAI_WEB_PORT"] = str(WEB_PORT)
    subprocess.run(cmd, cwd=WEB_PATH, env=env)
