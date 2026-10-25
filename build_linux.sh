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
pip install -q matplotlib numpy pandas pyinstaller

echo "[3/3] Сборка GUI..."
pyinstaller --onefile --windowed \
  --add-data "heat3d:." \
  --add-data "heat3d.cpp:." \
  --hidden-import report_plots \
  --name "HeatSim3D" \
  --clean \
  gui.py

echo
echo "Готово: dist/HeatSim3D   (запуск: ./dist/HeatSim3D или python3 gui.py)"
