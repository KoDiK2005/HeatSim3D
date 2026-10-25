#!/usr/bin/env bash
# Кросс-сборка Windows-ядра heat3d.exe из Linux (нужен mingw-w64:
#   sudo apt install g++-mingw-w64-x86-64-posix)
# -static — exe не требует DLL MinGW/libgomp на машине пользователя
set -e
cd "$(dirname "$0")"
x86_64-w64-mingw32-g++-posix -O2 -fopenmp -std=c++17 -static heat3d.cpp -o heat3d.exe
echo "Готово: heat3d.exe (Windows x64, OpenMP)"
