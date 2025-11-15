#!/usr/bin/env bash
set -e

echo "==== ЗАПУСК ВСЕХ СЦЕНАРИЕВ ===="

scripts/test_stage1.sh
scripts/test_stage2.sh
scripts/test_stage3.sh
scripts/test_stage4.sh
scripts/test_stage5.sh

echo
echo "==== ВСЕ СЦЕНАРИИ ВЫПОЛНЕНЫ ===="