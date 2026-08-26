#!/usr/bin/env sh
set -eu

CONTAINER_NAME=${CONTAINER_NAME:-demo-dubber}
IMAGE_NAME=${IMAGE_NAME:-demo-dubber-web}
REMOVE_IMAGE=${REMOVE_IMAGE:-0}

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but not installed." >&2
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -Fx "$CONTAINER_NAME" >/dev/null 2>&1; then
  echo "Stopping and removing $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME"
else
  echo "Container $CONTAINER_NAME not found"
fi

if [ "$REMOVE_IMAGE" != "1" ]; then
  echo "Keeping image $IMAGE_NAME. Set REMOVE_IMAGE=1 to remove it."
elif docker images --format '{{.Repository}}' | grep -Fx "$IMAGE_NAME" >/dev/null 2>&1; then
  echo "Removing image $IMAGE_NAME"
  docker rmi "$IMAGE_NAME"
else
  echo "Image $IMAGE_NAME not found"
fi
