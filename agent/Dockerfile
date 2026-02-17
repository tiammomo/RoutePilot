# =============================================================================
# ShuaiTravelAgent - Agent Dockerfile
# =============================================================================
# 多阶段构建，优化镜像大小
# =============================================================================

# 阶段1: 安装依赖
FROM python:3.10-slim AS builder

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制依赖文件
COPY agent/requirements.txt .

# 创建虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt


# 阶段2: 运行应用
FROM python:3.10-slim

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制应用代码
COPY agent/src ./agent/src
COPY agent/proto ./agent/proto
COPY run_agent.py ./
COPY config ./config

# 创建非 root 用户
RUN useradd -m -u 1000 agentuser && \
    chown -R agentuser:agentuser /app

USER agentuser

# 暴露端口
EXPOSE 50051

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:50051/health || exit 1

# 启动命令
CMD ["python", "run_agent.py"]
