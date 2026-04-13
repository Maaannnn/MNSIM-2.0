#!/usr/bin/env bash
set -euo pipefail

# repo root detection
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$ROOT_DIR"

# Remove macOS files and Python caches
find . -name .DS_Store -type f -delete
find . -type d -name __pycache__ -prune -exec rm -rf {} +
find . -type d -name .pytest_cache -prune -exec rm -rf {} +
find . -type d -name .mypy_cache -prune -exec rm -rf {} +
find . -type d -name .ruff_cache -prune -exec rm -rf {} +

# Optional: clear temp logs in artifacts
find artifacts -type f -name '*.log' -size -5M -delete 2>/dev/null || true

printf "Cleanup done.\n"
