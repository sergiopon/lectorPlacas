FROM node:22-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim@sha256:3dd7cc108ec1493442514f5c2a871af6af0ec31d768ff6e378a93340c3b3db5f
COPY --from=ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0t64 libsm6 && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never LECTOR_IN_CONTAINER=1 LECTOR_KEY_FILE=/app/keys/lector_key LECTOR_EXECUTION_PROVIDER=cpu LECTOR_PUBLIC_PORT=8765 PATH=/app/.venv/bin:$PATH
RUN groupadd --system --gid 10001 lector && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /app --shell /usr/sbin/nologin lector
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ src/
COPY config/ config/
RUN uv sync --locked --no-dev
RUN mkdir -p models data logs keys videos && chown lector:lector models data logs keys && chmod 0700 models data logs keys
USER lector
RUN lector models fetch && rm -rf logs/*
COPY --from=frontend /src/frontend/dist frontend/dist
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import os, urllib.request as u; p = os.environ.get('LECTOR_PUBLIC_PORT') or '8765'; u.urlopen(u.Request('http://127.0.0.1:8765/', headers={'Host': '127.0.0.1:' + p}), timeout=3)"
CMD ["lector-web", "--no-browser", "--port", "8765"]
