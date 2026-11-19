FROM ghcr.io/astral-sh/uv:0.13.9 AS uv

FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git liblua5.4-0 nodejs python3.12 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home tester \
    && install -d -o tester -g tester /workspace

COPY --from=uv /uv /usr/local/bin/uv
COPY run-tests.sh /usr/local/bin/spoken-tests

ENV UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    GIT_OPTIONAL_LOCKS=0 \
    SPOKEN_SOURCE=/input/spoken-wow

WORKDIR /workspace
USER tester
ENTRYPOINT ["bash", "/usr/local/bin/spoken-tests"]
