#!/usr/bin/env bash
set -e

run_case() {
  local cfg="$1"
  local title="$2"

  echo
  echo "===== ЭТАП 4: $title ====="
  cp "$cfg" config.yaml
  # 4 — порядок загрузки, 0 — выход из меню
  python main.py --stage 4
}

run_case "tests/configs/stage3_linear.yaml" \
         "порядок загрузки для линейного графа"

run_case "tests/configs/stage3_cycle.yaml" \
         "порядок загрузки при наличии цикла"
