#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
IMAGE_NAME=${IMAGE_NAME:-demo-dubber-web}
CONTAINER_NAME=${CONTAINER_NAME:-demo-dubber}
HOST_PORT=${HOST_PORT:-8000}
CONTAINER_PORT=8000
ENV_FILE=${ENV_FILE:-"$SCRIPT_DIR/.env"}
PREWARM_KOKORO=${PREWARM_KOKORO:-1}
PREWARM_WHISPER=${PREWARM_WHISPER:-1}
BUILD_RETRIES=${BUILD_RETRIES:-3}
HOST_OUTPUTS_DIR=${HOST_OUTPUTS_DIR:-"$SCRIPT_DIR/outputs"}
HOST_WORKSPACE_DIR=${HOST_WORKSPACE_DIR:-"$SCRIPT_DIR/workspace"}
# Use the freshly installed image trust store unless a custom bundle is explicitly supplied.
CA_BUNDLE=${CA_BUNDLE:-}

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

mkdir -p "$HOST_OUTPUTS_DIR" "$HOST_WORKSPACE_DIR"

HF_TOKEN_VALUE=${HF_TOKEN:-$(env_value HF_TOKEN "")}
KOKORO_VOICE_VALUE=${KOKORO_VOICE:-$(env_value KOKORO_VOICE af_heart)}
KOKORO_LANG_CODE_VALUE=${KOKORO_LANG_CODE:-$(env_value KOKORO_LANG_CODE a)}
KOKORO_REPO_ID_VALUE=${KOKORO_REPO_ID:-$(env_value KOKORO_REPO_ID hexgrad/Kokoro-82M)}
WHISPER_MODEL_VALUE=${DEMO_DUBBER_LOCAL_WHISPER_MODEL:-$(env_value DEMO_DUBBER_LOCAL_WHISPER_MODEL medium.en)}

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
    -f "$SCRIPT_DIR/Dockerfile.web" \
    --build-arg "PREWARM_KOKORO=$PREWARM_KOKORO" \
    --build-arg "PREWARM_WHISPER=$PREWARM_WHISPER" \
    --build-arg "KOKORO_VOICE=$KOKORO_VOICE_VALUE" \
    --build-arg "KOKORO_LANG_CODE=$KOKORO_LANG_CODE_VALUE" \
    --build-arg "KOKORO_REPO_ID=$KOKORO_REPO_ID_VALUE" \
    --build-arg "WHISPER_MODEL=$WHISPER_MODEL_VALUE" \
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

echo "Starting $CONTAINER_NAME on 127.0.0.1:$HOST_PORT"
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  --env-file "$ENV_FILE" \
  -e HF_HOME=/opt/huggingface \
  -e DEMO_DUBBER_LOCAL_WHISPER_DEVICE=cpu \
  -e DEMO_DUBBER_LOCAL_WHISPER_COMPUTE_TYPE=int8 \
  -e DEMO_DUBBER_OUTPUTS=/app/outputs \
  -e DEMO_DUBBER_WORKSPACE=/app/workspace \
  -p "127.0.0.1:${HOST_PORT}:${CONTAINER_PORT}" \
  -v "$HOST_OUTPUTS_DIR:/app/outputs" \
  -v "$HOST_WORKSPACE_DIR:/app/workspace" \
  "$IMAGE_NAME"

echo "Container: $CONTAINER_NAME"
echo "URL: http://127.0.0.1:${HOST_PORT}"
echo "Outputs volume: $HOST_OUTPUTS_DIR"
echo "Workspace volume: $HOST_WORKSPACE_DIR"
echo "Whisper and Kokoro models: baked into image $IMAGE_NAME"
