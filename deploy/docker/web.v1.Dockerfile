# syntax=docker/dockerfile:1.7
ARG NODE_BASE_IMAGE=node:24.17.0-alpine3.23
ARG NPM_VERSION=11.18.0

FROM ${NODE_BASE_IMAGE} AS dependencies
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./apps/web/
COPY packages/typescript/contracts_generated/package.json \
  ./packages/typescript/contracts_generated/package.json
RUN cd apps/web && npm ci --ignore-scripts


FROM dependencies AS build
ARG APP_BUILD_SHA=local
ARG APP_BUILD_CREATED_AT=unknown
ENV APP_BUILD_CREATED_AT=${APP_BUILD_CREATED_AT} \
    APP_BUILD_SHA=${APP_BUILD_SHA} \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production
COPY apps/web ./apps/web
COPY packages/typescript/contracts_generated ./packages/typescript/contracts_generated
RUN cd apps/web && npm run build && npm prune --omit=dev


FROM ${NODE_BASE_IMAGE} AS runtime
ARG APP_BUILD_SHA=local
ARG APP_BUILD_CREATED_AT=unknown
ARG NPM_VERSION
ENV APP_BUILD_CREATED_AT=${APP_BUILD_CREATED_AT} \
    APP_BUILD_SHA=${APP_BUILD_SHA} \
    HOSTNAME=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production \
    PORT=33003
LABEL org.opencontainers.image.title="RoutePilot Web V1" \
      org.opencontainers.image.description="Same-origin RoutePilot Next.js BFF and workbench" \
      org.opencontainers.image.revision=${APP_BUILD_SHA} \
      org.opencontainers.image.created=${APP_BUILD_CREATED_AT}

RUN npm install --global "npm@${NPM_VERSION}" && npm cache clean --force

WORKDIR /app/apps/web
COPY --from=build --chown=node:node /app/apps/web/.next ./.next
COPY --from=build --chown=node:node /app/apps/web/node_modules ./node_modules
COPY --from=build --chown=node:node /app/apps/web/package.json ./package.json

USER node
EXPOSE 33003
CMD ["npm", "run", "start"]
