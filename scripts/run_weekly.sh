#!/bin/bash
# 週次バッチ実行スクリプト
# cron例: 0 8 * * 0 /home/kazuu/work/investment-advisor/scripts/run_weekly.sh

set -euo pipefail

cd "$(dirname "$0")/.."

source .venv/bin/activate 2>/dev/null || true

python -m investment_advisor.main
