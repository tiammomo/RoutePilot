# =============================================================================
# ShuaiTravelAgent - Web Dockerfile
# =============================================================================
# 多阶段构建，优化镜像大小
# =============================================================================

# 阶段1: 安装依赖
FROM python:3.10-slim AS builder

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 创建虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt


# 阶段2: 运行应用
FROM python:3.10-slim

WORKDIR /app

# 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制应用代码
COPY web/src ./src

# 创建非 root 用户
RUN useradd -m -u 1000 webuser && \
    chown -R webuser:webuser /app

USER webuser

# 设置 PYTHONPATH
ENV PYTHONPATH=/app

# 暴露端口
EXPOSE 48081

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:48081/api/health || exit 1

# 启动命令 - 使用 python -m uvicorn
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "48081"]
