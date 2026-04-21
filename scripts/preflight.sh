#!/usr/bin/env bash
# Runs every CI deterministic gate locally, in the same order CI runs them.
# Intended use: invoke before every `git push` on feat/* branches.
#
# Convention, not hook: CI is still the source of truth. This script's only
# job is to catch the "all green locally, red on CI" class of failure cheaply.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../backend"
cd "$BACKEND_DIR"

echo "==> ruff check (lint)"
uv run ruff check .

echo "==> ruff format --check"
uv run ruff format --check .

echo "==> mypy --strict"
uv run mypy --strict .

echo "==> pytest"
uv run pytest

echo ""
echo "All gates green."
