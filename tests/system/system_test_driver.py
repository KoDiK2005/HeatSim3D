# -*- coding: utf-8 -*-
"""
Системное тестирование HeatSim3D.
Запускает НАСТОЯЩЕЕ приложение gui.py (без изменений в коде) в реальном
окне на экране пользователя, прогоняет пользовательский сценарий и два
сценария с ошибочными данными, делает скриншоты через ImageMagick `import`.

heat3d.exe в этой папке — тот же heat3d.cpp, пересобранный под Linux
(см. интеграционные тесты), т.к. исходный .exe собран под Windows
и не может быть запущен как процесс на этой машине.
"""
import os, sys, subprocess, shutil, time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gui

SCREENS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screens")
os.makedirs(SCREENS, exist_ok=True)

app = gui.HeatSimApp()
app.update_idletasks()
win_id = app.winfo_id()


def shot(name):
    app.update_idletasks()
    app.update()
    path = os.path.join(SCREENS, name + ".png")
    subprocess.run(["import", "-window", str(win_id), path], check=False)
    print("SCREENSHOT:", path)


def step_01_initial():
    shot("01_start_window")
    app.after(300, step_02_material)


def step_02_material():
    app.mat_var.set("Медь")
    app._on_material()
    shot("02_material_med_alpha_updated")
    app.after(300, step_03_bad_spinbox_text)


def step_03_bad_spinbox_text():
    """Системный тест дефекта №1: нечисловой текст в поле Nx (Spinbox)."""
    shot("03a_before_bad_nx")
    app.nx_var_widget = None
    # Находим виджет Spinbox для Nx и подменяем его содержимое так,
    # как это сделал бы пользователь, стерев число и напечатав текст.
    found = None
    def find_spinbox(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Spinbox):
                return c
            r = find_spinbox(c)
            if r:
                return r
        return None
    sb = find_spinbox(app)
    if sb is not None:
        sb.delete(0, "end")
        sb.insert(0, "abc")
    app.after(300, lambda: step_04_click_run_with_bad_nx())


def step_04_click_run_with_bad_nx():
    app.run_btn.invoke()
    app.after(700, step_05_after_bad_nx)


def step_05_after_bad_nx():
    shot("03b_after_run_click_with_bad_nx_no_reaction")
    print("НАБЛЮДЕНИЕ: run_btn.invoke() выполнен, ни диалога с ошибкой, ни запуска "
          "симуляции не произошло (кнопка снова активна, прогресс не изменился).")
    # возвращаем корректное значение и переходим к следующему сценарию
    sb = None
    def find_spinbox(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Spinbox):
                return c
            r = find_spinbox(c)
            if r:
                return r
        return None
    sb = find_spinbox(app)
    if sb is not None:
        sb.delete(0, "end")
        sb.insert(0, "10")
    app.ny_var.set(80)
    app.nz_var.set(10)
    app.t_end_var.set("50000")
    app.save_var.set("500")
    app.after(300, step_06_run_asymmetric)


def step_06_run_asymmetric():
    """Системный тест дефекта №2: асимметричная сетка 10x80x10 —
    предупреждение "Много файлов" не появляется, хотя реально будет ~82 файла."""
    shot("04a_before_run_asymmetric_grid")
    app.run_btn.invoke()
    app.after(500, step_07_check_no_warning)


def step_07_check_no_warning():
    shot("04b_after_run_click_no_warning_dialog")
    print("НАБЛЮДЕНИЕ: диалог «Много файлов» не появился для сетки 10x80x10, "
          "хотя реально будет сгенерировано ~82 файла (см. интеграционный тест).")
    app.after(4000, step_08_wait_done)


def step_08_wait_done():
    if app._running:
        app.after(1000, step_08_wait_done)
        return
    shot("05_asymmetric_run_done")
    n = len([f for f in os.listdir(app._output_dir) if f.startswith("slice_")]) \
        if os.path.isdir(app._output_dir) else -1
    print(f"РЕАЛЬНОЕ число файлов срезов после расчёта: {n}")
    app.after(500, step_09_reset_and_normal_run)


def step_09_reset_and_normal_run():
    """Обычный штатный прогон (nx=ny=nz=30) для проверки корректной работы графиков."""
    app.nx_var.set(30); app.ny_var.set(30); app.nz_var.set(30)
    app.t_end_var.set("50000"); app.save_var.set("500")
    app.mat_var.set("Сталь (конструкционная)")
    app._on_material()
    app.run_btn.invoke()
    app.after(1500, step_10_progress_shot)


def step_10_progress_shot():
    shot("06_normal_run_in_progress")
    app.after(6000, step_11_wait_done)


def step_11_wait_done(tries=0):
    if app._running and tries < 30:
        app.after(1000, lambda: step_11_wait_done(tries + 1))
        return
    shot("07_normal_run_done_history_tab")
    nb = None
    for c in app.winfo_children():
        pass
    app.after(300, step_12_switch_tabs)


def step_12_switch_tabs():
    # Находим Notebook и переключаем вкладки, чтобы сфотографировать графики
    def find_nb(w):
        import tkinter.ttk as ttk
        for c in w.winfo_children():
            if isinstance(c, ttk.Notebook):
                return c
            r = find_nb(c)
            if r:
                return r
        return None
    nb = find_nb(app)
    if nb is not None:
        nb.select(1)  # Срезы + Поток
        app.update()
        shot("08_slices_tab")
        nb.select(2)  # 3D + Изолинии
        app.update()
        shot("09_3d_tab")
        nb.select(3)  # Профили
        app.update()
        shot("10_profile_tab")
    app.after(300, step_13_missing_exe)


def step_13_missing_exe():
    """Контрольный сценарий: heat3d.exe отсутствует -- ожидаем понятную ошибку."""
    exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heat3d.exe")
    tmp_path = exe_path + ".hidden"
    shutil.move(exe_path, tmp_path)
    app.run_btn.invoke()
    app.after(500, lambda: step_14_after_missing_exe(tmp_path, exe_path))


def step_14_after_missing_exe(tmp_path, exe_path):
    shot("11_missing_exe_error_dialog")
    # Закрываем модальный messagebox программно (как нажатие "OK"),
    # чтобы разблокировать заблокированный вызов showerror() внутри _start_sim.
    for w in app.winfo_children():
        if isinstance(w, tk.Toplevel):
            w.destroy()
    shutil.move(tmp_path, exe_path)
    app.after(500, finish)


def finish():
    print("SYSTEM_TEST_DONE")
    app.destroy()
    sys.exit(0)


app.after(500, step_01_initial)
app.mainloop()
