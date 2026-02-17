# 阶段1: 安装依赖
FROM node:20-alpine AS deps
WORKDIR /app

# 复制依赖文件
COPY package.json package-lock.json* ./

# 安装依赖
RUN npm ci

# 阶段2: 构建应用
FROM node:20-alpine AS builder
WORKDIR /app

# 复制依赖和源代码
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# 构建
RUN npm run build

# 阶段3: 运行应用
FROM node:20-alpine AS runner
WORKDIR /app

# 创建非 root 用户
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# 复制构建产物（standalone 模式）
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./

# 设置环境变量
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=43001
ENV HOSTNAME="0.0.0.0"
ENV NEXT_PUBLIC_API_BASE=http://web:48081

# 切换用户
USER nextjs

# 暴露端口
EXPOSE 43001

# 启动命令
CMD ["node", "server.js"]
