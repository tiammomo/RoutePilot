ARG NODE_BASE_IMAGE=node:22-alpine

FROM ${NODE_BASE_IMAGE} AS deps
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci

FROM ${NODE_BASE_IMAGE} AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY frontend/. .
ARG NEXT_PUBLIC_API_BASE=http://localhost:38083
ARG INTERNAL_API_BASE=http://backend:38083
ARG APP_BUILD_SHA=local
ARG APP_BUILD_CREATED_AT=
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
ENV INTERNAL_API_BASE=${INTERNAL_API_BASE}
RUN npm run build

FROM ${NODE_BASE_IMAGE} AS runner
WORKDIR /app
ARG APP_BUILD_SHA=local
ARG APP_BUILD_CREATED_AT=
ENV NODE_ENV=production
ENV PORT=33003
ENV HOSTNAME=0.0.0.0
ENV APP_BUILD_SHA=${APP_BUILD_SHA}
ENV APP_BUILD_CREATED_AT=${APP_BUILD_CREATED_AT}
LABEL org.opencontainers.image.title="moyuan-travel-agent Frontend" \
      org.opencontainers.image.description="Next.js frontend for moyuan-travel-agent" \
      org.opencontainers.image.revision=${APP_BUILD_SHA} \
      org.opencontainers.image.created=${APP_BUILD_CREATED_AT}
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 33003

CMD ["node", "server.js"]
