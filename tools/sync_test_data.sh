#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$ROOT_DIR"

SRC_DIR="测试数据"
DST_DIR="test_data"
MODE="forward"

usage() {
  echo "Usage: $0 [-r]"
  echo "  No flag : sync 中文 → 英文 (测试数据 → test_data)"
  echo "  -r      : sync 英文 → 中文 (test_data → 测试数据)"
}

while getopts ":rh" opt; do
  case "$opt" in
    r) MODE="reverse" ;;
    h) usage; exit 0 ;;
    *) usage; exit 1 ;;
  esac
done

mkdir -p "$SRC_DIR" "$DST_DIR"

if [[ "$MODE" == "forward" ]]; then
  rsync -a --delete "$SRC_DIR/" "$DST_DIR/"
  echo "Synced: $SRC_DIR → $DST_DIR"
else
  rsync -a --delete "$DST_DIR/" "$SRC_DIR/"
  echo "Synced: $DST_DIR → $SRC_DIR"
fi
