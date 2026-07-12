# syntax=docker/dockerfile:1.7
# PostGIS 3.5.2 / PostgreSQL 17 image manifest inspected on 2026-07-12.
ARG POSTGIS_BASE_IMAGE=postgis/postgis:17-3.5@sha256:6916f5cc87001fa99bc44dbaa3f906d60ef7c813074e943ae4a3cd5a94a16947

FROM ${POSTGIS_BASE_IMAGE} AS vector-build
ARG PGVECTOR_VERSION=0.8.5
ARG PGVECTOR_ARCHIVE_SHA256=6f88a5cbdde31666f4b6c1a6b75c51dcbeffe58f9a7d2b26e502d5a6e5e14d44
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential ca-certificates curl postgresql-server-dev-17 && \
    curl --fail --location --silent --show-error \
      "https://github.com/pgvector/pgvector/archive/refs/tags/v${PGVECTOR_VERSION}.tar.gz" \
      --output /tmp/pgvector.tar.gz && \
    echo "${PGVECTOR_ARCHIVE_SHA256}  /tmp/pgvector.tar.gz" | sha256sum --check --strict && \
    mkdir /tmp/pgvector && \
    tar --extract --gzip --file /tmp/pgvector.tar.gz --directory /tmp/pgvector \
      --strip-components=1 && \
    make -C /tmp/pgvector OPTFLAGS="" && \
    make -C /tmp/pgvector install


FROM ${POSTGIS_BASE_IMAGE}
ARG PGVECTOR_VERSION=0.8.5
LABEL org.opencontainers.image.title="RoutePilot PostgreSQL V1" \
      org.opencontainers.image.description="PostgreSQL 17 with PostGIS 3.5 and pgvector" \
      org.opencontainers.image.version="postgres17-postgis3.5-pgvector${PGVECTOR_VERSION}"
COPY --from=vector-build /usr/lib/postgresql/17/lib/vector.so \
  /usr/lib/postgresql/17/lib/vector.so
COPY --from=vector-build /usr/lib/postgresql/17/lib/bitcode/vector \
  /usr/lib/postgresql/17/lib/bitcode/vector
COPY --from=vector-build /usr/lib/postgresql/17/lib/bitcode/vector.index.bc \
  /usr/lib/postgresql/17/lib/bitcode/vector.index.bc
COPY --from=vector-build /usr/share/postgresql/17/extension/vector.control \
  /usr/share/postgresql/17/extension/vector.control
COPY --from=vector-build /usr/share/postgresql/17/extension/vector--*.sql \
  /usr/share/postgresql/17/extension/
