#!/usr/bin/env bash
# Сборка HeatSim3D под Linux: расчётное ядро heat3d (OpenMP) + GUI в один файл
#   ./build_linux.sh          — ядро + GUI (dist/HeatSim3D)
#   ./build_linux.sh engine   — только ядро heat3d
# Нужны: g++ (с поддержкой OpenMP), python3, python3-tk, pip
set -e
cd "$(dirname "$0")"

echo "[1/3] Расчётное ядро heat3d (OpenMP)..."
g++ -O2 -fopenmp -std=c++17 heat3d.cpp -o heat3d
[ "$1" = "engine" ] && { echo "Готово: ./heat3d"; exit 0; }

echo "[2/3] Python-зависимости..."
# Ubuntu 24.04+ (PEP 668) не даёт ставить пакеты в системный python — живём в venv.
# Отдельный venv без системных пакетов: matplotlib из apt не содержит своих
# шрифтов (mpl-data ссылается на /usr/share), и в собранном файле пропадает
# кириллица. tkinter входит в стандартную библиотеку и в venv доступен и так.
VENV=.venv-build
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q matplotlib numpy pandas pyinstaller

echo "[3/3] Сборка GUI..."
# Все параметры сборки — в HeatSim3D.spec (общий для Linux и Windows)
"$VENV/bin/pyinstaller" --clean -y HeatSim3D.spec

echo
echo "Готово: dist/HeatSim3D   (запуск: ./dist/HeatSim3D или python3 gui.py)"
