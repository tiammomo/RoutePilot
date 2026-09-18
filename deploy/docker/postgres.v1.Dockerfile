# syntax=docker/dockerfile:1.7
# PostgreSQL 17.11 / Debian 12 manifest inspected on 2026-09-18.
ARG POSTGRES_BASE_IMAGE=postgres:17-bookworm@sha256:051f7b7b3abdd564d5d1bd1e8c4b9c1b6e77087d1dd22020ede611c096a272e0
FROM ${POSTGRES_BASE_IMAGE}

# PGDG packages are authenticated by the base image's signed repository.
# Keep extension binaries and SQL upgrade scripts on the same reviewed version.
ARG POSTGIS_PACKAGE_VERSION=3.6.4+dfsg-2.pgdg12+1
ARG PGVECTOR_PACKAGE_VERSION=0.8.5-1.pgdg12+1
RUN apt-get -o APT::Update::Error-Mode=any update && \
    apt-get install -y --no-install-recommends \
      "postgresql-17-postgis-3=${POSTGIS_PACKAGE_VERSION}" \
      "postgresql-17-postgis-3-scripts=${POSTGIS_PACKAGE_VERSION}" \
      "postgresql-17-pgvector=${PGVECTOR_PACKAGE_VERSION}" && \
    rm -rf /var/lib/apt/lists/*

LABEL org.opencontainers.image.title="RoutePilot PostgreSQL V1" \
      org.opencontainers.image.description="PostgreSQL 17 with PostGIS 3.6 and pgvector 0.8.5" \
      org.opencontainers.image.version="postgres17-postgis${POSTGIS_PACKAGE_VERSION}-pgvector${PGVECTOR_PACKAGE_VERSION}"

# The RoutePilot init script creates extensions and roles in POSTGRES_DB.
# Existing volumes require the reviewed upgrade procedure in v1-platform.md.
COPY deploy/security/postgres-v1-smoke.sql /usr/local/share/routepilot/postgres-v1-smoke.sql
