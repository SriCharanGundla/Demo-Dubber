FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_VERSION=0.8.17 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120 \
    UV_HTTP_RETRIES=5 \
    UV_NATIVE_TLS=1 \
    UV_INSECURE_HOST=download.pytorch.org \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    HF_HOME=/opt/huggingface \
    HF_HUB_DISABLE_XET=1 \
    HF_HUB_DOWNLOAD_TIMEOUT=120 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=6767

WORKDIR /app

ARG PREWARM_KOKORO=1
ARG KOKORO_VOICE=af_heart
ARG KOKORO_LANG_CODE=a
ARG KOKORO_REPO_ID=hexgrad/Kokoro-82M

ENV KOKORO_VOICE=$KOKORO_VOICE \
    KOKORO_LANG_CODE=$KOKORO_LANG_CODE \
    KOKORO_REPO_ID=$KOKORO_REPO_ID

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Docker images do not inherit the host's trusted corporate/proxy CAs.  The
# deploy script supplies its effective CA bundle as a BuildKit secret so HTTPS
# clients used both during the build and at runtime retain certificate checks.
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -f /run/secrets/ca_bundle ]; then \
      cp /run/secrets/ca_bundle /etc/ssl/certs/ca-certificates.crt; \
    fi

RUN python -m pip install "uv==$UV_VERSION"

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --native-tls --allow-insecure-host download.pytorch.org

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    uv run python -m pip install \
    --trusted-host github.com \
    --trusted-host objects.githubusercontent.com \
    --trusted-host release-assets.githubusercontent.com \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

COPY scripts/prewarm_kokoro.py scripts/prewarm_kokoro.py
RUN mkdir -p "$HF_HOME"
RUN --mount=type=secret,id=hf_token \
    if [ "$PREWARM_KOKORO" = "1" ]; then \
      if [ -f /run/secrets/hf_token ]; then export HF_TOKEN="$(cat /run/secrets/hf_token)"; fi; \
      uv run python scripts/prewarm_kokoro.py; \
    else \
      echo "Skipping Kokoro prewarm during build"; \
    fi

# Keep application changes from invalidating the large, network-dependent
# dependency and model layers above. Only this inexpensive layer should rebuild
# for normal source or configuration-example edits.
COPY . .

EXPOSE 6767

CMD ["uv", "run", "--frozen", "python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=6767"]
