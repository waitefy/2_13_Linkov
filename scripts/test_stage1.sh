#!/usr/bin/env bash
set -e

run_case_ok() {
  local cfg="$1"
  local title="$2"

  echo
  echo "===== ЭТАП 1: $title ====="
  cp "$cfg" config.yaml
  python main.py --stage 1
}

run_case_expect_fail() {
  local cfg="$1"
  local title="$2"

  echo
  echo "===== ЭТАП 1: $title (ОЖИДАЕМАЯ ОШИБКА) ====="
  cp "$cfg" config.yaml

  # временно отключаем "падать при ошибке"
  set +e
  python main.py --stage 1
  echo "----- конец ожидаемой ошибки -----"
  # включаем обратно
  set -e
}

run_case_ok "tests/configs/stage1_ok.yaml" \
            "корректная конфигурация"

run_case_expect_fail "tests/configs/stage1_missing_version.yaml" \
                     "ошибка: отсутствует version"
