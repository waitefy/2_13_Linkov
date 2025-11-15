#!/usr/bin/env bash
set -e

run_case() {
  local cfg="$1"
  local title="$2"

  echo
  echo "===== ЭТАП 3: $title ====="
  cp "$cfg" config.yaml
  # 3 — граф зависимостей, 0 — выход из меню
  python main.py --stage 3
}

run_case "tests/configs/stage3_linear.yaml" \
         "линейный граф A -> B -> C"

run_case "tests/configs/stage3_branch.yaml" \
         "ветвящийся граф"

run_case "tests/configs/stage3_cycle.yaml" \
         "граф с циклом"

run_case "tests/configs/stage3_extra.yaml" \
         "граф с недостижимыми узлами"
