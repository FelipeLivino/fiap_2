#!/usr/bin/env bash
set -euo pipefail

echo "== Disco =="
df -h /
echo

echo "== Memoria =="
free -h
echo

echo "== Python =="
python3 --version
python3 -m pip --version
echo

echo "== Recomendacao =="
AVAILABLE_KB="$(df --output=avail / | tail -1 | tr -d ' ')"
AVAILABLE_GB="$(python3 - <<PY
print(round(int("$AVAILABLE_KB") / 1024 / 1024, 2))
PY
)"

echo "Espaco livre aproximado: ${AVAILABLE_GB} GB"
python3 - <<PY
available_gb = float("$AVAILABLE_GB")
if available_gb < 3:
    print("Pouco espaco para Ultralytics + Torch. Use OpenCV ou libere espaco antes.")
else:
    print("Espaco parece suficiente para tentar instalar o modelo com --no-cache-dir.")
PY
