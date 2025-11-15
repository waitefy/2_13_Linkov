#!/usr/bin/env bash
set -e

run_case_ok() {
  local cfg="$1"
  local title="$2"

  echo
  echo "===== ЭТАП 2: $title ====="
  cp "$cfg" config.yaml
  # 2 — прямые зависимости, 0 — выход из меню
  python main.py --stage 2
}

run_case_expect_fail() {
  local cfg="$1"
  local title="$2"

  echo
  echo "===== ЭТАП 2: $title (ОЖИДАЕМАЯ ОШИБКА) ====="
  cp "$cfg" config.yaml

  # временно разрешаем ненулевой код выхода
  set +e
  python main.py --stage 2
  echo "----- конец ожидаемой ошибки -----"
  set -e
}

# Успешный сценарий (режим real)
run_case_ok "tests/configs/stage2_real.yaml" \
            "прямые зависимости NuGet-пакета Newtonsoft.Json"

# Демонстрация ошибки режима (опционально, если сделал конфиг)
run_case_expect_fail "tests/configs/stage2_wrong_mode.yaml" \
                    "ошибка: test_mode != real"
