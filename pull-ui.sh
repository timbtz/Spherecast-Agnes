#!/usr/bin/env bash
# Pull latest Lovable frontend changes and rebuild
# Run this whenever you iterate on the design in Lovable and want to sync here.
set -e

echo "[pull-ui] Pulling from agnes-ai-navigator..."
git subtree pull \
  --prefix=orchestration/ui \
  https://github.com/timbtz/agnes-ai-navigator.git \
  main \
  --squash

echo "[pull-ui] Installing dependencies..."
cd orchestration/ui
bun install

echo "[pull-ui] Building..."
bun run build

echo "[pull-ui] Done. Restart FastAPI to pick up the new build."
