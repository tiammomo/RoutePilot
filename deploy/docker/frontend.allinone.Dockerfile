# Build stage
FROM node:20-alpine AS builder
WORKDIR /app

# Copy package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY frontend/. .

# Build Python backend
COPY backend /app/backend
COPY agent /app/agent
COPY requirements.txt /app/
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt
WORKDIR /app/frontend

# Expose ports
EXPOSE 3000 8000

# Start both services
CMD ["sh", "-c", "npm run dev & PYTHONPATH=/app:/app/backend python -m uvicorn moyuan_web.main:app --host 0.0.0.0 --port 38083 --app-dir /app/backend"]
