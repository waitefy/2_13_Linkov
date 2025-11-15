#!/usr/bin/env bash
set -e

run_case() {
  local cfg="$1"
  local title="$2"

  echo
  echo "===== ЭТАП 5: $title ====="
  cp "$cfg" config.yaml
  # 5 — визуализация, 0 — выход
  python main.py --stage 5
}

run_case "tests/configs/stage3_linear.yaml" \
         "визуализация линейного графа"

run_case "tests/configs/stage3_branch.yaml" \
         "визуализация ветвящегося графа"

run_case "tests/configs/stage3_cycle.yaml" \
         "визуализация графа с циклом"
