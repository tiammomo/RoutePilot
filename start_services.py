"""启动所有服务的脚本"""
import subprocess
import sys
import os
import time

def find_conda_python():
    """查找 conda 环境的 Python"""
    possible_paths = [
        r"D:\anaconda\envs\agents\python.exe",
        r"D:\codes\anaconda\envs\agents\python.exe",
        r"C:\anaconda\envs\agents\python.exe",
        r"C:\ProgramData\anaconda3\envs\agents\python.exe",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return sys.executable  # 回退到系统 Python

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    python_path = find_conda_python()

    print(f"Project root: {project_root}")
    print(f"Python: {python_path}")

    # 启动 Agent
    print("\n[*] Starting Agent service...")
    agent_proc = subprocess.Popen(
        [python_path, "run_agent.py"],
        cwd=project_root,
        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
    )
    print(f"    Agent started, PID: {agent_proc.pid}")

    # 等待 Agent 启动
    time.sleep(5)

    # 启动 API
    print("[*] Starting API service...")
    api_proc = subprocess.Popen(
        [python_path, "run_api.py"],
        cwd=project_root,
        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
    )
    print(f"    API started, PID: {api_proc.pid}")

    print("\n[OK] All services started!")
    print("    Agent: localhost:50051")
    print("    API: localhost:38000")
    print("    Frontend: localhost:33001 (run separately: cd frontend && npm run dev)")

if __name__ == "__main__":
    main()
