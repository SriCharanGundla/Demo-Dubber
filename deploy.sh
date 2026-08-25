#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
IMAGE_NAME=${IMAGE_NAME:-demo-dubber}
CONTAINER_NAME=${CONTAINER_NAME:-demo-dubber}
HOST_PORT=${HOST_PORT:-6767}
CONTAINER_PORT=6767
ENV_FILE=${ENV_FILE:-"$SCRIPT_DIR/.env"}
PREWARM_KOKORO=${PREWARM_KOKORO:-1}
BUILD_RETRIES=${BUILD_RETRIES:-3}
DATA_ROOT=${DATA_ROOT:-"$SCRIPT_DIR/.docker-data"}
HOST_OUTPUTS_DIR=${HOST_OUTPUTS_DIR:-"$DATA_ROOT/outputs"}
HOST_WORKSPACE_DIR=${HOST_WORKSPACE_DIR:-"$DATA_ROOT/workspace"}
HOST_HF_CACHE_DIR=${HOST_HF_CACHE_DIR:-"$DATA_ROOT/huggingface"}
CA_BUNDLE=${CA_BUNDLE:-${SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}}

env_value() {
  key=$1
  fallback=$2
  value=$fallback

  while IFS= read -r line; do
    case "$line" in
      "$key="*) value=${line#*=} ;;
    esac
  done < "$ENV_FILE"

  value=${value#\'}
  value=${value%\'}
  value=${value#\"}
  value=${value%\"}
  printf '%s' "$value"
}

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but not installed." >&2
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

mkdir -p "$HOST_OUTPUTS_DIR" "$HOST_WORKSPACE_DIR" "$HOST_HF_CACHE_DIR"

HF_TOKEN_VALUE=${HF_TOKEN:-$(env_value HF_TOKEN "")}
KOKORO_VOICE_VALUE=${KOKORO_VOICE:-$(env_value KOKORO_VOICE af_heart)}
KOKORO_LANG_CODE_VALUE=${KOKORO_LANG_CODE:-$(env_value KOKORO_LANG_CODE a)}
KOKORO_REPO_ID_VALUE=${KOKORO_REPO_ID:-$(env_value KOKORO_REPO_ID hexgrad/Kokoro-82M)}

HF_TOKEN_SECRET_FILE=""
if [ -n "$HF_TOKEN_VALUE" ]; then
  umask 077
  HF_TOKEN_SECRET_FILE=$(mktemp "${TMPDIR:-/tmp}/demo-dubber-hf-token.XXXXXX")
  printf '%s' "$HF_TOKEN_VALUE" > "$HF_TOKEN_SECRET_FILE"
fi

cleanup() {
  if [ -n "$HF_TOKEN_SECRET_FILE" ]; then
    rm -f "$HF_TOKEN_SECRET_FILE"
  fi
}
trap cleanup EXIT INT TERM

docker_build() {
  set --
  if [ -f "$CA_BUNDLE" ]; then
    set -- "$@" --secret "id=ca_bundle,src=$CA_BUNDLE"
  fi

  if [ -n "$HF_TOKEN_SECRET_FILE" ]; then
    set -- "$@" --secret "id=hf_token,src=$HF_TOKEN_SECRET_FILE"
  fi

  docker build \
    "$@" \
    --build-arg "PREWARM_KOKORO=$PREWARM_KOKORO" \
    --build-arg "KOKORO_VOICE=$KOKORO_VOICE_VALUE" \
    --build-arg "KOKORO_LANG_CODE=$KOKORO_LANG_CODE_VALUE" \
    --build-arg "KOKORO_REPO_ID=$KOKORO_REPO_ID_VALUE" \
    -t "$IMAGE_NAME" \
    "$SCRIPT_DIR"
}

echo "Building image $IMAGE_NAME from $SCRIPT_DIR"
attempt=1
while :; do
  if docker_build; then
    break
  fi

  if [ "$attempt" -ge "$BUILD_RETRIES" ]; then
    echo "Docker build failed after $attempt attempt(s)." >&2
    echo "Check the failing download above. For TLS interception, set CA_BUNDLE to the trusted PEM bundle." >&2
    exit 1
  fi

  attempt=$((attempt + 1))
  echo "Docker build failed. Retrying attempt $attempt/$BUILD_RETRIES in 5 seconds..." >&2
  sleep 5
done

if docker ps -a --format '{{.Names}}' | grep -Fx "$CONTAINER_NAME" >/dev/null 2>&1; then
  echo "Removing existing container $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

echo "Starting $CONTAINER_NAME on 0.0.0.0:$HOST_PORT"
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  --env-file "$ENV_FILE" \
  -p "0.0.0.0:${HOST_PORT}:${CONTAINER_PORT}" \
  -v "$HOST_OUTPUTS_DIR:/app/outputs" \
  -v "$HOST_WORKSPACE_DIR:/app/workspace" \
  -v "$HOST_HF_CACHE_DIR:/opt/huggingface" \
  "$IMAGE_NAME"

echo "Container: $CONTAINER_NAME"
echo "URL: http://0.0.0.0:${HOST_PORT}"
echo "Outputs volume: $HOST_OUTPUTS_DIR"
echo "Workspace volume: $HOST_WORKSPACE_DIR"
echo "Hugging Face cache volume: $HOST_HF_CACHE_DIR"
