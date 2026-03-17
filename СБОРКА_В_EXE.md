# Сборка GUI в .exe — пошаговая инструкция

## Структура папки (всё должно быть в одном месте)

```
HeatSim3D/
├── gui.py           ← этот файл
├── heat3d.cpp       ← исходник симулятора (нужен для перекомпиляции)
├── heat3d.exe       ← скомпилированный симулятор (из Visual Studio)
└── build_exe.bat    ← скрипт сборки (запустить один раз)
```

---

## Шаг 1 — Установить Python-зависимости

Открой **cmd** или **PowerShell** и выполни:

```bat
pip install matplotlib numpy pandas pyinstaller
```

---

## Шаг 2 — Собрать .exe

Просто запусти файл **build_exe.bat** двойным кликом.

Или вручную в cmd из папки HeatSim3D:

```bat
pyinstaller --onefile --windowed ^
  --add-data "heat3d.exe;." ^
  --add-data "heat3d.cpp;." ^
  --name "HeatSim3D" ^
  gui.py
```

Флаги:
- `--onefile`   — всё в один .exe файл
- `--windowed`  — без консольного окна
- `--add-data`  — включить heat3d.exe и .cpp внутрь сборки

---

## Шаг 3 — Результат

После сборки в папке `dist/` появится файл:

```
dist/
└── HeatSim3D.exe   ← готово к запуску!
```

Этот `.exe` можно скопировать куда угодно и запустить двойным кликом — Python устанавливать не нужно.

---

## Альтернатива: запустить без сборки

Если Python уже установлен — можно просто запустить:

```bat
python gui.py
```

---

## Возможные проблемы

| Проблема | Решение |
|----------|---------|
| `g++ не найден` | Установи MinGW: https://winlibs.com/ и добавь в PATH |
| `ModuleNotFoundError` | `pip install matplotlib numpy pandas` |
| Антивирус блокирует .exe | Добавь папку dist/ в исключения |
| Окно мигает и закрывается | Запусти через cmd, посмотри ошибку |
