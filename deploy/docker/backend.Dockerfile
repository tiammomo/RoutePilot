ARG PYTHON_BASE_IMAGE=python:3.13-slim
FROM ${PYTHON_BASE_IMAGE}

ARG APP_BUILD_SHA=local
ARG APP_BUILD_CREATED_AT=

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/backend \
    APP_BUILD_SHA=${APP_BUILD_SHA} \
    APP_BUILD_CREATED_AT=${APP_BUILD_CREATED_AT}

LABEL org.opencontainers.image.title="moyuan-travel-agent Backend" \
      org.opencontainers.image.description="FastAPI backend for moyuan-travel-agent" \
      org.opencontainers.image.revision=${APP_BUILD_SHA} \
      org.opencontainers.image.created=${APP_BUILD_CREATED_AT}

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY agent ./agent
COPY backend ./backend
COPY scripts ./scripts

RUN mkdir -p /app/data /app/logs

EXPOSE 38083

CMD ["python", "-m", "uvicorn", "moyuan_web.main:app", "--host", "0.0.0.0", "--port", "38083", "--app-dir", "backend"]
