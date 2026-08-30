#!/usr/bin/env bash
# 공개 저장소에 포함된 Terraform 경계 검사만 실행한다.
set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

cd "$(dirname "$0")/.."

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
elif command -v python.exe >/dev/null 2>&1; then
  PYTHON=python.exe
else
  printf 'Python 3 실행 파일을 찾을 수 없습니다.\n' >&2
  exit 127
fi

"$PYTHON" -B scripts/check_lab_static.py --root .
"$PYTHON" -B -m unittest tests.test_lab_static
"$PYTHON" -B scripts/check_serverless_mlops_static.py --root .
"$PYTHON" -B -m unittest tests.test_serverless_mlops_static
"$PYTHON" -B scripts/check_serverless_opendart_static.py --root .
"$PYTHON" -B -m unittest tests.test_serverless_opendart_static

printf '공개 Terraform 경계 검사: PASS (6/6)\n'
