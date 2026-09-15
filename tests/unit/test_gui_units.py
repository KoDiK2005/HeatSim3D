# -*- coding: utf-8 -*-
"""
Модульные тесты для gui.py (HeatSim3D)
Тестируем отдельные функции/методы изолированно, без полноценного запуска окна.
Запуск: python3 test_gui_units.py
"""
import sys, os, tkinter as tk

sys.path.insert(0, "/home/mark/Документы/HeatSim3D")
import gui  # noqa: E402

ok = 0
total = 0

def check(cond, name):
    global ok, total
    total += 1
    print(("  [OK]   " if cond else "  [ФЕЙЛ] ") + name)
    if cond:
        ok += 1

print("=" * 50)
print(" ЧАСТЬ 1. ТЕСТЫ КОРРЕКТНОСТИ (ожидаем OK)")
print("=" * 50)

print("\n-- resource_path(): путь к ресурсу рядом со скриптом --")
p = gui.resource_path("heat3d.exe")
check(p.endswith(os.path.join("HeatSim3D", "heat3d.exe")) or p.endswith("heat3d.exe"),
      "resource_path('heat3d.exe') формирует путь рядом с gui.py")

print("\n-- find_exe(): находит существующий heat3d.exe --")
found = gui.find_exe()
check(found is not None and os.path.exists(found),
      "find_exe() находит heat3d.exe в папке проекта")

print("\n-- _build_cmd(): формирование аргументов командной строки для heat3d.exe --")
params = {
    "nx": 40, "ny": 40, "nz": 40,
    "alpha": 1.28e-5, "t_end": 50000.0, "t_init": 20.0,
    "t_xm": 100.0, "t_xp": 100.0, "t_ym": 100.0, "t_yp": 100.0,
    "t_zm": 100.0, "t_zp": 100.0, "save_every": 500,
}
cmd = gui.HeatSimApp._build_cmd(None, "heat3d.exe", params)
check(cmd[0] == "heat3d.exe", "первый элемент команды — путь к exe")
check("--nx" in cmd and cmd[cmd.index("--nx") + 1] == "40", "--nx передан верно")
check("--alpha" in cmd and cmd[cmd.index("--alpha") + 1] == "1.280000e-05",
      "--alpha передан в формате %.6e")

print("=" * 50)
print(" ЧАСТЬ 2. ДЕМОНСТРАЦИЯ НАЙДЕННЫХ ОШИБОК")
print(" (тест намеренно воспроизводит дефект и подтверждает его)")
print("=" * 50)

root = tk.Tk()
root.withdraw()  # не показываем окно, оно не нужно для этого теста

print("\n-- Дефект №1: поле Nx (Spinbox) не проверяет диапазон при ручном вводе --")
# Именно так создаётся Spinbox для Nx в gui.py (_spinrow, gui.py:397-402) —
# параметры from_=5, to=80 передаются, но validate НЕ задан.
nx_var = tk.IntVar(value=30)
sb = tk.Spinbox(root, from_=5, to=80, textvariable=nx_var)
sb.delete(0, "end")
sb.insert(0, "9999")  # пользователь вручную вбивает значение далеко за пределами [5,80]
value_accepted = nx_var.get()
print(f"  Введено в поле Nx: '9999' (лимит по ТЗ виджета: 5..80)")
print(f"  nx_var.get() вернул: {value_accepted}")
print("  ПРОБЛЕМА: Spinbox создан без validate='key'/'focusout', поэтому диапазон")
print("  from_/to_ только двигает стрелочки, но НЕ ограничивает ручной ввод текста.")
check(value_accepted == 9999, "подтверждено: значение вне [5,80] принято без предупреждения")

print("\n-- Дефект №2: нечисловой ввод в Nx вызывает TclError, а не ValueError --")
sb.delete(0, "end")
sb.insert(0, "abc")
raised_type = None
try:
    nx_var.get()
except Exception as e:
    raised_type = type(e).__name__
print("  Введено в поле Nx: 'abc'")
print(f"  nx_var.get() выбросил исключение типа: {raised_type}")
print("  ПРОБЛЕМА: _get_params() в gui.py (строка 428) перехватывает только ValueError:")
print("      except ValueError as e: messagebox.showerror(...)")
print("  а IntVar.get() на нечисловом тексте кидает _tkinter.TclError,")
print("  который НЕ является ValueError -> messagebox не покажется, приложение")
print("  просто «не отреагирует» на нажатие Запустить без объяснения причины.")
check(raised_type == "TclError", "подтверждено: тип исключения TclError не перехватывается кодом gui.py")

root.destroy()

print("=" * 50)
print(f" ИТОГО: {ok} / {total} проверок подтвердили ожидаемое поведение")
print("=" * 50)
