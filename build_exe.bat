@echo off
echo ============================================
echo  Сборка HeatSim3D.exe
echo ============================================

echo.
echo [1/3] Проверка PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Устанавливаю PyInstaller...
    pip install pyinstaller
)

echo [1.5/3] Расчётное ядро heat3d.exe (OpenMP)...
where g++ >nul 2>&1
if errorlevel 1 (
    echo g++ ^(MinGW^) не найден - используется готовый heat3d.exe
) else (
    g++ -O2 -fopenmp -std=c++17 -static heat3d.cpp -o heat3d.exe
)

echo [2/3] Сборка .exe...
pyinstaller --onefile --windowed ^
  --add-data "heat3d.exe;." ^
  --add-data "heat3d.cpp;." ^
  --hidden-import report_plots ^
  --name "HeatSim3D" ^
  --clean ^
  gui.py

echo.
echo [3/3] Готово!
echo.
echo Исполняемый файл: dist\HeatSim3D.exe
echo.
pause
