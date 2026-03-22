"""
gui.py — Графический интерфейс для 3D моделирования теплопроводности
=======================================================================
Параметры из GUI передаются в heat3d.exe через аргументы командной строки.

Зависимости:
    pip install matplotlib numpy pandas

Сборка в .exe:
    pip install pyinstaller
    pyinstaller --onefile --windowed --add-data "heat3d.exe;." --name "HeatSim3D" gui.py

Требует: heat3d.exe в той же папке
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import os
import sys
import re
import gc
import glob

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec

# ─── Цветовая схема ──────────────────────────────────────────────────────────
C = {
    "bg":        "#0d1117",
    "panel":     "#161b22",
    "border":    "#30363d",
    "accent":    "#58a6ff",
    "accent2":   "#f78166",
    "success":   "#3fb950",
    "warning":   "#d29922",
    "text":      "#e6edf3",
    "text_dim":  "#8b949e",
    "input_bg":  "#21262d",
    "btn":       "#238636",
    "btn_hover": "#2ea043",
    "btn_stop":  "#b62324",
}

CMAP = "inferno"

# ─── Материалы-пресеты ────────────────────────────────────────────────────────
MATERIALS = {
    "Сталь (конструкционная)": 1.28e-5,
    "Сталь (нержавеющая)":     3.91e-6,
    "Алюминий":                8.42e-5,
    "Медь":                    1.17e-4,
    "Титан":                   2.90e-6,
    "Чугун":                   6.67e-6,
    "Бетон":                   5.71e-7,
    "Гранит":                  1.40e-6,
    "Кирпич":                  5.20e-7,
}


def resource_path(name):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def find_exe():
    candidates = [
        resource_path("heat3d.exe"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "heat3d.exe"),
        "heat3d.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


# ══════════════════════════════════════════════════════════════════════════════
class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 30
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.geometry(f"+{x}+{y}")
        tk.Label(self.tw, text=self.text, background="#1c2128",
                 foreground=C["text_dim"], relief="flat",
                 font=("Consolas", 9), padx=6, pady=4).pack()

    def hide(self, _=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None


# ══════════════════════════════════════════════════════════════════════════════
class HeatSimApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HeatSim 3D  —  Моделирование теплопроводности")
        self.configure(bg=C["bg"])
        self.geometry("1280x820")
        self.minsize(1000, 700)
        self.resizable(True, True)

        self._proc = None
        self._running = False
        self._cmap = "inferno"
        self._output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "output")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._late_init)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        hdr = tk.Frame(self, bg=C["bg"], pady=12)
        hdr.pack(fill="x", padx=20)
        tk.Label(hdr, text="HeatSim 3D",
                 font=("Consolas", 20, "bold"),
                 bg=C["bg"], fg=C["accent"]).pack(side="left")
        tk.Label(hdr, text="  Явная схема FTCS  ·  Уравнение Фурье–Кирхгофа",
                 font=("Consolas", 10),
                 bg=C["bg"], fg=C["text_dim"]).pack(side="left")

        tk.Button(hdr, text=" ? ", font=("Consolas", 11, "bold"),
                  bg=C["input_bg"], fg=C["accent"], relief="flat",
                  activebackground=C["border"], activeforeground=C["accent"],
                  cursor="hand2", padx=6,
                  command=self._show_about).pack(side="right", padx=4)

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")

        main = tk.Frame(self, bg=C["bg"])
        main.pack(fill="both", expand=True, padx=20, pady=12)

        # Левая панель — с прокруткой
        left_outer = tk.Frame(main, bg=C["panel"], bd=0,
                              highlightthickness=1,
                              highlightbackground=C["border"],
                              width=310)
        left_outer.pack(side="left", fill="y", padx=(0, 12))
        left_outer.pack_propagate(False)

        # Canvas + Scrollbar для прокрутки содержимого
        left_canvas = tk.Canvas(left_outer, bg=C["panel"],
                                highlightthickness=0, width=308)
        left_canvas.pack(side="left", fill="both", expand=True)

        left_sb = ttk.Scrollbar(left_outer, orient="vertical",
                                command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_sb.set)

        left = tk.Frame(left_canvas, bg=C["panel"])
        left_window = left_canvas.create_window(
            (0, 0), window=left, anchor="nw", width=308)

        def _on_frame_configure(e):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))

        def _on_canvas_configure(e):
            left_canvas.itemconfig(left_window, width=e.width)

        def _on_mousewheel(e):
            left_canvas.yview_scroll(int(-1*(e.delta/120)), "units")

        left.bind("<Configure>", _on_frame_configure)
        left_canvas.bind("<Configure>", _on_canvas_configure)
        left_canvas.bind("<MouseWheel>", _on_mousewheel)
        left.bind("<MouseWheel>", _on_mousewheel)

        self._build_params(left)

        # Показываем scrollbar только если контент не помещается
        def _check_scrollbar(e=None):
            left_canvas.update_idletasks()
            if left_canvas.winfo_height() < left.winfo_reqheight():
                left_sb.pack(side="right", fill="y")
            else:
                left_sb.pack_forget()
        left.bind("<Configure>", lambda e: [_on_frame_configure(e),
                                             _check_scrollbar()])

        # Правая панель
        right = tk.Frame(main, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)
        self._build_plots(right)

    def _build_params(self, parent):
        tk.Label(parent, text="ПАРАМЕТРЫ СИМУЛЯЦИИ",
                 font=("Consolas", 9, "bold"),
                 bg=C["panel"], fg=C["text_dim"]).pack(
            anchor="w", padx=16, pady=(14, 8))

        # Материал
        self._section(parent, "Материал")
        self.mat_var = tk.StringVar(value=list(MATERIALS.keys())[0])
        mat_cb = ttk.Combobox(parent, textvariable=self.mat_var,
                              values=list(MATERIALS.keys()),
                              state="readonly", font=("Consolas", 10))
        mat_cb.pack(fill="x", padx=16, pady=(2, 8))
        mat_cb.bind("<<ComboboxSelected>>", self._on_material)

        # Сетка
        self._section(parent, "Сетка (узлы)")
        grid_f = tk.Frame(parent, bg=C["panel"])
        grid_f.pack(fill="x", padx=16, pady=(2, 8))
        self.nx_var = self._spinrow(grid_f, "Nx", 30, 5, 80, 0)
        self.ny_var = self._spinrow(grid_f, "Ny", 30, 5, 80, 1)
        self.nz_var = self._spinrow(grid_f, "Nz", 30, 5, 80, 2)

        # Физика
        self._section(parent, "Физические параметры")
        self.alpha_var = self._entry_row(
            parent, "α  (м²/с)", "1.28e-05",
            "Коэффициент температуропроводности")
        self.t_end_var = self._entry_row(
            parent, "t_end  (с)", "50000",
            "Общее время моделирования")

        # Температуры
        self._section(parent, "Начальная температура (°C)")
        self.t_init_var = self._entry_row(
            parent, "T начальная", "20",
            "Начальная температура внутри тела")

        self._section(parent, "Граничные условия (°C)")
        bc_frame = tk.Frame(parent, bg=C["panel"])
        bc_frame.pack(fill="x", padx=16, pady=(2, 4))

        # Сетка 3x2: X-/X+, Y-/Y+, Z-/Z+
        labels = ["X−", "X+", "Y−", "Y+", "Z−", "Z+"]
        defaults = [100, 100, 100, 100, 100, 100]
        self.bc_vars = []
        for col in range(2):
            bc_frame.columnconfigure(col*2+1, weight=1)
        for n, (lbl, dflt) in enumerate(zip(labels, defaults)):
            row, col = divmod(n, 2)
            var = tk.StringVar(value=str(dflt))
            self.bc_vars.append(var)
            tk.Label(bc_frame, text=lbl, font=("Consolas", 9, "bold"),
                     bg=C["panel"], fg=C["accent"], width=3, anchor="e"
                     ).grid(row=row, column=col*2, padx=(4,2), pady=2, sticky="e")
            tk.Entry(bc_frame, textvariable=var, font=("Consolas", 9),
                     bg=C["input_bg"], fg=C["text"],
                     insertbackground=C["accent"], relief="flat",
                     highlightthickness=1, highlightbackground=C["border"],
                     width=7
                     ).grid(row=row, column=col*2+1, padx=(0,8), pady=2, sticky="ew")

        # Частота сохранения
        self._section(parent, "Частота сохранения")
        self.save_var = self._entry_row(
            parent, "Каждые N шагов", "500",
            "Как часто сохранять срезы в CSV")

        # Цветовая палитра
        self._section(parent, "Цветовая палитра")
        self.cmap_var = tk.StringVar(value="inferno")
        cmaps = ["inferno", "plasma", "viridis", "magma",
                 "hot", "coolwarm", "RdYlBu_r", "jet"]
        cmap_cb = ttk.Combobox(parent, textvariable=self.cmap_var,
                               values=cmaps, state="readonly",
                               font=("Consolas", 10))
        cmap_cb.pack(fill="x", padx=16, pady=(2, 8))
        self._cmap_cb = cmap_cb  # сохраняем ссылку для позднего bind

        # Превью палитры
        self.cmap_preview = tk.Canvas(parent, height=18,
                                       bg=C["input_bg"],
                                       highlightthickness=0)
        self.cmap_preview.pack(fill="x", padx=16, pady=(0, 8))
        # превью рисуется после полной инициализации

        # Прогресс
        tk.Frame(parent, bg=C["border"], height=1).pack(fill="x", pady=10)
        self.progress_lbl = tk.Label(
            parent, text="Ожидание запуска...",
            font=("Consolas", 9), bg=C["panel"], fg=C["text_dim"])
        self.progress_lbl.pack(anchor="w", padx=16)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Heat.Horizontal.TProgressbar",
                        troughcolor=C["input_bg"], background=C["accent"],
                        thickness=6, borderwidth=0)
        self.progress = ttk.Progressbar(
            parent, style="Heat.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=16, pady=(4, 12))

        # Кнопки
        btn_f = tk.Frame(parent, bg=C["panel"])
        btn_f.pack(fill="x", padx=16, pady=(0, 8))

        self.run_btn = tk.Button(
            btn_f, text="▶  Запустить",
            font=("Consolas", 11, "bold"),
            bg=C["btn"], fg="white", relief="flat",
            activebackground=C["btn_hover"], activeforeground="white",
            cursor="hand2", pady=8,
            command=self._start_sim)
        self.run_btn.pack(fill="x", pady=(0, 6))

        self.stop_btn = tk.Button(
            btn_f, text="■  Остановить",
            font=("Consolas", 10),
            bg=C["input_bg"], fg=C["text_dim"], relief="flat",
            activebackground=C["btn_stop"], activeforeground="white",
            cursor="hand2", pady=6, state="disabled",
            command=self._stop_sim)
        self.stop_btn.pack(fill="x")

        # Лог
        tk.Frame(parent, bg=C["border"], height=1).pack(fill="x", pady=(8, 4))
        tk.Label(parent, text="ЛОГ", font=("Consolas", 8, "bold"),
                 bg=C["panel"], fg=C["text_dim"]).pack(anchor="w", padx=16)

        log_frame = tk.Frame(parent, bg=C["input_bg"],
                             highlightthickness=1,
                             highlightbackground=C["border"])
        log_frame.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        self.log_text = tk.Text(
            log_frame, bg=C["input_bg"], fg=C["text_dim"],
            font=("Consolas", 8), relief="flat",
            state="disabled", wrap="word", height=8)
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_plots(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure("TNotebook", background=C["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", background=C["panel"],
                        foreground=C["text_dim"], font=("Consolas", 10),
                        padding=[12, 6])
        style.map("TNotebook.Tab",
                  background=[("selected", C["bg"])],
                  foreground=[("selected", C["accent"])])

        self.tab_history = tk.Frame(nb, bg=C["bg"])
        self.tab_slices  = tk.Frame(nb, bg=C["bg"])
        self.tab_3d      = tk.Frame(nb, bg=C["bg"])
        self.tab_profile = tk.Frame(nb, bg=C["bg"])
        self.tab_compare = tk.Frame(nb, bg=C["bg"])

        nb.add(self.tab_history, text="  Динамика T  ")
        nb.add(self.tab_slices,  text="  Срезы + Поток  ")
        nb.add(self.tab_3d,      text="  3D + Изолинии  ")
        nb.add(self.tab_profile, text="  Профили  ")
        nb.add(self.tab_compare, text="  Сравнение  ")

        for tab in [self.tab_history, self.tab_slices,
                    self.tab_3d, self.tab_profile]:
            self._placeholder(tab)

        self._build_compare_tab()

    def _placeholder(self, tab):
        for w in tab.winfo_children():
            w.destroy()
        tk.Label(tab,
                 text="Запустите симуляцию для отображения графиков",
                 font=("Consolas", 13), bg=C["bg"], fg=C["text_dim"]
                 ).pack(expand=True)

    # ── Вспомогательные виджеты ───────────────────────────────────────────────
    def _section(self, parent, title):
        f = tk.Frame(parent, bg=C["panel"])
        f.pack(fill="x", padx=16, pady=(8, 2))
        tk.Label(f, text=title.upper(), font=("Consolas", 8, "bold"),
                 bg=C["panel"], fg=C["text_dim"]).pack(anchor="w")
        tk.Frame(f, bg=C["border"], height=1).pack(fill="x", pady=(2, 0))

    def _spinrow(self, parent, label, default, from_, to, row):
        var = tk.IntVar(value=default)
        tk.Label(parent, text=label, font=("Consolas", 9),
                 bg=C["panel"], fg=C["text"]).grid(
            row=row, column=0, sticky="w", pady=2)
        tk.Spinbox(parent, from_=from_, to=to, textvariable=var,
                   font=("Consolas", 10), bg=C["input_bg"],
                   fg=C["text"], insertbackground=C["accent"],
                   relief="flat", buttonbackground=C["border"],
                   width=6).grid(row=row, column=1, sticky="e",
                                 padx=(8, 0), pady=2)
        parent.columnconfigure(1, weight=1)
        return var

    def _entry_row(self, parent, label, default, tooltip=""):
        var = tk.StringVar(value=str(default))
        row = tk.Frame(parent, bg=C["panel"])
        row.pack(fill="x", padx=16, pady=2)
        lbl = tk.Label(row, text=label, font=("Consolas", 9),
                       bg=C["panel"], fg=C["text"], width=16, anchor="w")
        lbl.pack(side="left")
        tk.Entry(row, textvariable=var, font=("Consolas", 10),
                 bg=C["input_bg"], fg=C["text"],
                 insertbackground=C["accent"], relief="flat",
                 highlightthickness=1, highlightbackground=C["border"],
                 highlightcolor=C["accent"]).pack(
            side="left", fill="x", expand=True)
        if tooltip:
            Tooltip(lbl, tooltip)
        return var

    def _on_material(self, _=None):
        alpha = MATERIALS.get(self.mat_var.get(), 1.28e-5)
        self.alpha_var.set(f"{alpha:.3e}")

    # ── Сбор параметров и формирование команды ────────────────────────────────
    def _get_params(self):
        try:
            bc = [float(v.get()) for v in self.bc_vars]
            return {
                "nx":         int(self.nx_var.get()),
                "ny":         int(self.ny_var.get()),
                "nz":         int(self.nz_var.get()),
                "alpha":      float(self.alpha_var.get()),
                "t_end":      float(self.t_end_var.get()),
                "t_init":     float(self.t_init_var.get()),
                "t_xm": bc[0], "t_xp": bc[1],
                "t_ym": bc[2], "t_yp": bc[3],
                "t_zm": bc[4], "t_zp": bc[5],
                "save_every": int(self.save_var.get()),
            }
        except ValueError as e:
            messagebox.showerror("Ошибка параметров", f"Неверный формат: {e}")
            return None

    def _build_cmd(self, exe, p):
        """Строит список аргументов для запуска heat3d.exe с параметрами из GUI."""
        return [
            exe,
            "--nx",         str(p["nx"]),
            "--ny",         str(p["ny"]),
            "--nz",         str(p["nz"]),
            "--alpha",      f"{p['alpha']:.6e}",
            "--t_end",      str(p["t_end"]),
            "--t_init",     str(p["t_init"]),
            "--t_xm",       str(p["t_xm"]),
            "--t_xp",       str(p["t_xp"]),
            "--t_ym",       str(p["t_ym"]),
            "--t_yp",       str(p["t_yp"]),
            "--t_zm",       str(p["t_zm"]),
            "--t_zp",       str(p["t_zp"]),
            "--save_every", str(p["save_every"]),
        ]

    # ── Запуск симуляции ──────────────────────────────────────────────────────
    def _start_sim(self):
        p = self._get_params()
        if not p:
            return

        exe = find_exe()
        if exe is None:
            messagebox.showerror(
                "heat3d.exe не найден",
                "Положите heat3d.exe в ту же папку что и gui.py")
            return

        # Предупреждение если будет слишком много файлов
        try:
            from math import sqrt
            dx = 1.0 / (p["nx"] - 1)
            dt_est = 0.4 / (2.0 * p["alpha"] * 3.0 / (dx*dx))
            n_files = int(p["t_end"] / dt_est / p["save_every"]) + 1
            if n_files > 50:
                from tkinter import messagebox as mb
                ans = mb.askyesno("Много файлов",
                    f"Расчёт создаст ~{n_files} CSV файлов.\n"
                    f"Это может занять много памяти.\n\n"
                    f"Увеличь 'Каждые N шагов' чтобы сократить их число.\n\n"
                    f"Продолжить?")
                if not ans:
                    return
        except Exception:
            pass

        cmd = self._build_cmd(exe, p)
        self._log("Запуск: " + " ".join(cmd))

        self._running = True
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress["value"] = 0
        self.progress_lbl.config(text="Запуск...", fg=C["accent"])

        for tab in [self.tab_history, self.tab_slices,
                    self.tab_3d, self.tab_profile]:
            self._placeholder(tab)

        threading.Thread(
            target=self._run_thread,
            args=(exe, cmd),
            daemon=True
        ).start()

    def _run_thread(self, exe, cmd):
        try:
            workdir = os.path.dirname(os.path.abspath(exe))
            # Очищаем папку output перед новым запуском
            out_dir_clean = os.path.join(workdir, "output")
            if os.path.exists(out_dir_clean):
                import shutil
                for f in os.listdir(out_dir_clean):
                    if f.endswith(".csv"):
                        os.remove(os.path.join(out_dir_clean, f))

            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=workdir,
                bufsize=1,
                encoding="utf-8",
                errors="replace"
            )

            total_steps = None

            for line in self._proc.stdout:
                line = line.rstrip()
                self._log(line)

                m = re.search(r"Steps\s*:\s*(\d+)", line)
                if m:
                    total_steps = int(m.group(1))

                m = re.search(r"step=\s*(\d+)", line)
                if m and total_steps:
                    step = int(m.group(1))
                    pct  = min(100, step / total_steps * 100)
                    lbl  = f"Шаг {step}/{total_steps}"
                    mt = re.search(r"t=\s*([\d\.]+)", line)
                    mc = re.search(r"T_center=\s*([\d\.]+)", line)
                    if mt:
                        lbl += f"  ·  t={float(mt.group(1)):.0f}с"
                    if mc:
                        lbl += f"  ·  Tc={float(mc.group(1)):.1f}°C"
                    self.after(0, self._set_progress, pct, lbl)

            self._proc.wait()
            ok = (self._proc.returncode == 0)
            out = os.path.join(workdir, "output")
            self.after(0, self._sim_done, ok, out)

        except Exception as e:
            self._log(f"[ОШИБКА] {e}")
            self.after(0, self._sim_done, False, "")

    def _set_progress(self, pct, lbl):
        self.progress["value"] = pct
        self.progress_lbl.config(text=lbl)

    def _stop_sim(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._log("[ОСТАНОВЛЕНО пользователем]")
        self._sim_done(False, "")

    def _sim_done(self, success, out_dir):
        self._running = False
        self.run_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        if success:
            self.progress["value"] = 100
            self.progress_lbl.config(text="Завершено успешно", fg=C["success"])
            self._output_dir = out_dir
            self._draw_all(out_dir)
        else:
            self.progress_lbl.config(text="Остановлено / ошибка", fg=C["warning"])

    # ── Лог ───────────────────────────────────────────────────────────────────
    def _log(self, msg):
        def _do():
            self.log_text.config(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.after(0, _do)

    # ── Графики ───────────────────────────────────────────────────────────────
    def _draw_all(self, out_dir):
        self._draw_history(out_dir)
        self._draw_slices(out_dir)
        self._draw_3d(out_dir)
        self._draw_profiles(out_dir)

    def _embed_fig(self, tab, fig):
        import matplotlib.pyplot as plt
        # Закрываем старые фигуры чтобы освободить память
        for w in tab.winfo_children():
            w.destroy()
        plt.close("all")
        gc.collect()
        canvas = FigureCanvasTkAgg(fig, master=tab)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        return canvas

    def _ax_style(self, ax):
        ax.set_facecolor(C["panel"])
        ax.tick_params(colors=C["text_dim"], labelsize=8)
        for sp in ax.spines.values():
            sp.set_color(C["border"])
        ax.grid(color=C["border"], linestyle="--", alpha=0.5)

    # Вкладка 1 — История T
    def _draw_history(self, out_dir):
        path = os.path.join(out_dir, "history.csv")
        if not os.path.exists(path):
            return
        df = pd.read_csv(path)

        fig = Figure(figsize=(10, 5), facecolor=C["bg"])
        gs  = GridSpec(1, 2, figure=fig, wspace=0.4)

        for i, (col, label, color) in enumerate([
            ("T_center", "T в центре тела [°C]", C["accent2"]),
            ("T_mean",   "Средняя T по объёму [°C]", C["accent"]),
        ]):
            ax = fig.add_subplot(gs[0, i])
            self._ax_style(ax)

            t_vals = df[col]
            t_min  = float(t_vals.min())
            t_max  = float(t_vals.max())
            t_start = float(t_vals.iloc[0])
            t_end_v = float(t_vals.iloc[-1])
            time_at_min = float(df["time"].iloc[t_vals.idxmin()])
            time_at_max = float(df["time"].iloc[t_vals.idxmax()])

            ax.plot(df["time"], t_vals, color=color, linewidth=2)
            ax.fill_between(df["time"], t_vals, t_min,
                            alpha=0.12, color=color)

            # Линия нуля если пересекает
            if t_min < 0 < t_max:
                ax.axhline(y=0, color=C["border"],
                           linewidth=0.8, linestyle=":")

            # Аннотация MIN
            ax.annotate(
                f"min = {t_min:.1f}°C",
                xy=(time_at_min, t_min),
                xytext=(10, 12), textcoords="offset points",
                color=C["accent2"], fontsize=8, fontweight="bold",
                arrowprops=dict(arrowstyle="->",
                                color=C["accent2"], lw=1.0))

            # Аннотация MAX
            ax.annotate(
                f"max = {t_max:.1f}°C",
                xy=(time_at_max, t_max),
                xytext=(10, -18), textcoords="offset points",
                color=C["success"], fontsize=8, fontweight="bold",
                arrowprops=dict(arrowstyle="->",
                                color=C["success"], lw=1.0))

            # Стартовое и конечное значение
            ax.text(0.02, 0.04,
                    f"Начало: {t_start:.1f}°C  →  Конец: {t_end_v:.1f}°C"
                    f"  (Δ = {t_end_v - t_start:+.1f}°C)",
                    transform=ax.transAxes,
                    color=C["text_dim"], fontsize=8)

            ax.set_xlabel("Время [с]", color=C["text_dim"], fontsize=9)
            ax.set_ylabel(label, color=C["text_dim"], fontsize=9)
            ax.set_title(label, color=C["text"], fontsize=10)

        self._embed_fig(self.tab_history, fig)

    def _draw_slices(self, out_dir):
        """Срезы XY и XZ финального шага + вектор теплового потока на XY"""
        import glob as gl
        z_files = sorted(gl.glob(os.path.join(out_dir, "slice_z_step*.csv")))
        y_files = sorted(gl.glob(os.path.join(out_dir, "slice_y_step*.csv")))
        if not z_files or not y_files:
            return

        df_xy = pd.read_csv(z_files[-1])
        df_xz = pd.read_csv(y_files[-1])
        step  = int(re.search(r"step(\d+)", z_files[-1]).group(1))

        # Диапазон из финальных срезов (не читаем все файлы)
        all_T = pd.concat([df_xy["T"], df_xz["T"]])
        vmin, vmax = float(all_T.min()), float(all_T.max())
        del all_T
        if abs(vmax - vmin) < 0.01:
            vmin -= 1.0; vmax += 1.0

        fig = Figure(figsize=(14, 9), facecolor=C["bg"])
        gs  = GridSpec(2, 2, figure=fig, wspace=0.35, hspace=0.45)

        # ── Срез XY (тепловая карта) ─────────────────────────────────────────
        piv_xy = df_xy.pivot_table(index="y", columns="x", values="T")
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.set_facecolor(C["panel"])
        T_range = float(piv_xy.values.max()) - float(piv_xy.values.min())
        if T_range < 0.01:
            ax1.imshow([[float(piv_xy.values.mean())]], cmap=self._cmap,
                       vmin=vmin, vmax=vmax, origin="lower",
                       aspect="equal", extent=[0,1,0,1])
            ax1.text(0.5, 0.5, f"T ≈ {float(piv_xy.values.mean()):.1f}°C",
                     ha="center", va="center", color="white",
                     fontsize=11, transform=ax1.transAxes)
        else:
            im1 = ax1.imshow(piv_xy.values, origin="lower", aspect="equal",
                             cmap=self._cmap, vmin=vmin, vmax=vmax,
                             extent=[0,1,0,1])
            cb1 = fig.colorbar(im1, ax=ax1, fraction=0.046, pad=0.04)
            cb1.ax.tick_params(colors=C["text_dim"], labelsize=7)
            cb1.set_label("T [°C]", color=C["text_dim"], fontsize=7)
        ax1.set_title(f"Срез XY  (z=L/2)  —  шаг {step}",
                      color=C["text"], fontsize=10)
        ax1.set_xlabel("x [м]", color=C["text_dim"], fontsize=9)
        ax1.set_ylabel("y [м]", color=C["text_dim"], fontsize=9)
        ax1.tick_params(colors=C["text_dim"], labelsize=7)
        for sp in ax1.spines.values(): sp.set_color(C["border"])

        # ── Вектор теплового потока q = -grad(T) на срезе XY ────────────────
        ax2 = fig.add_subplot(gs[0, 1])
        ax2.set_facecolor(C["panel"])
        if T_range >= 0.01:
            Z_xy = piv_xy.values
            # Градиент: dT/dy, dT/dx (numpy возвращает [row, col] = [y, x])
            grad_y, grad_x = np.gradient(Z_xy)
            # Поток q = -grad(T) (тепло течёт от горячего к холодному)
            qx = -grad_x
            qy = -grad_y

            # Прореживаем стрелки (каждые N узлов)
            ny, nx = Z_xy.shape
            step_arr = max(2, nx // 12)
            xi = np.linspace(0, 1, nx)
            yi = np.linspace(0, 1, ny)
            Xi, Yi = np.meshgrid(xi, yi)

            xs = Xi[::step_arr, ::step_arr]
            ys = Yi[::step_arr, ::step_arr]
            us = qx[::step_arr, ::step_arr]
            vs = qy[::step_arr, ::step_arr]

            # Фон — тепловая карта
            im2 = ax2.imshow(Z_xy, origin="lower", aspect="equal",
                             cmap=self._cmap, vmin=vmin, vmax=vmax,
                             extent=[0,1,0,1], alpha=0.75)

            # Нормируем длину стрелок для красивого отображения
            magnitude = np.sqrt(us**2 + vs**2)
            mag_max = magnitude.max()
            if mag_max > 0:
                us_n = us / mag_max
                vs_n = vs / mag_max

            ax2.quiver(xs, ys, us_n, vs_n,
                       color="white", alpha=0.85,
                       scale=18, width=0.003,
                       headwidth=4, headlength=5)

            cb2 = fig.colorbar(im2, ax=ax2, fraction=0.046, pad=0.04)
            cb2.ax.tick_params(colors=C["text_dim"], labelsize=7)
            cb2.set_label("T [°C]", color=C["text_dim"], fontsize=7)
        else:
            ax2.text(0.5, 0.5, "Поле однородное\nПоток = 0",
                     ha="center", va="center", color=C["text_dim"],
                     fontsize=12, transform=ax2.transAxes)

        ax2.set_title("Вектор теплового потока  q = −∇T",
                      color=C["text"], fontsize=10)
        ax2.set_xlabel("x [м]", color=C["text_dim"], fontsize=9)
        ax2.set_ylabel("y [м]", color=C["text_dim"], fontsize=9)
        ax2.tick_params(colors=C["text_dim"], labelsize=7)
        for sp in ax2.spines.values(): sp.set_color(C["border"])

        # ── Срез XZ (тепловая карта) ─────────────────────────────────────────
        piv_xz = df_xz.pivot_table(index="z", columns="x", values="T")
        ax3 = fig.add_subplot(gs[1, 0])
        ax3.set_facecolor(C["panel"])
        T_range_xz = float(piv_xz.values.max()) - float(piv_xz.values.min())
        if T_range_xz < 0.01:
            ax3.imshow([[float(piv_xz.values.mean())]], cmap=self._cmap,
                       vmin=vmin, vmax=vmax, origin="lower",
                       aspect="equal", extent=[0,1,0,1])
            ax3.text(0.5, 0.5, f"T ≈ {float(piv_xz.values.mean()):.1f}°C",
                     ha="center", va="center", color="white",
                     fontsize=11, transform=ax3.transAxes)
        else:
            im3 = ax3.imshow(piv_xz.values, origin="lower", aspect="equal",
                             cmap=self._cmap, vmin=vmin, vmax=vmax,
                             extent=[0,1,0,1])
            cb3 = fig.colorbar(im3, ax=ax3, fraction=0.046, pad=0.04)
            cb3.ax.tick_params(colors=C["text_dim"], labelsize=7)
            cb3.set_label("T [°C]", color=C["text_dim"], fontsize=7)
        ax3.set_title(f"Срез XZ  (y=L/2)  —  шаг {step}",
                      color=C["text"], fontsize=10)
        ax3.set_xlabel("x [м]", color=C["text_dim"], fontsize=9)
        ax3.set_ylabel("z [м]", color=C["text_dim"], fontsize=9)
        ax3.tick_params(colors=C["text_dim"], labelsize=7)
        for sp in ax3.spines.values(): sp.set_color(C["border"])

        # ── Профиль T(x) при y=0.5, z=L/2 с min/max ─────────────────────────
        ax4 = fig.add_subplot(gs[1, 1])
        ax4.set_facecolor(C["panel"])
        px = df_xy[df_xy["y"].between(0.48, 0.52)].sort_values("x")
        if not px.empty:
            ax4.plot(px["x"], px["T"], color=C["accent"], linewidth=2)
            ax4.fill_between(px["x"], px["T"], alpha=0.15, color=C["accent"])
            t_min = float(px["T"].min())
            t_max = float(px["T"].max())
            t_min_x = float(px.loc[px["T"].idxmin(), "x"])
            t_max_x = float(px.loc[px["T"].idxmax(), "x"])
            ax4.axhline(t_min, color=C["accent2"], linestyle=":", linewidth=1.2)
            ax4.axhline(t_max, color=C["success"], linestyle=":", linewidth=1.2)
            ax4.annotate(f"min = {t_min:.1f}°C",
                         xy=(t_min_x, t_min), xytext=(0.05, 0.12),
                         textcoords="axes fraction",
                         color=C["accent2"], fontsize=8,
                         arrowprops=dict(arrowstyle="->",
                                         color=C["accent2"], lw=1))
            ax4.annotate(f"max = {t_max:.1f}°C",
                         xy=(t_max_x, t_max), xytext=(0.55, 0.88),
                         textcoords="axes fraction",
                         color=C["success"], fontsize=8,
                         arrowprops=dict(arrowstyle="->",
                                         color=C["success"], lw=1))
        ax4.set_xlabel("x [м]", color=C["text_dim"], fontsize=9)
        ax4.set_ylabel("T [°C]", color=C["text_dim"], fontsize=9)
        ax4.set_title("Профиль T(x)  при y=0.5, z=L/2",
                      color=C["text"], fontsize=10)
        ax4.tick_params(colors=C["text_dim"], labelsize=7)
        for sp in ax4.spines.values(): sp.set_color(C["border"])
        ax4.grid(color=C["border"], linestyle="--", alpha=0.5)

        fig.tight_layout(pad=1.5)
        self._embed_fig(self.tab_slices, fig)

    def _draw_3d(self, out_dir):
        from mpl_toolkits.mplot3d import Axes3D  # noqa

        files = sorted(glob.glob(os.path.join(out_dir, "slice_z_step*.csv")))
        if not files:
            return
        df   = pd.read_csv(files[-1])
        step = int(re.search(r"step(\d+)", files[-1]).group(1))
        piv  = df.pivot_table(index="y", columns="x", values="T")
        X, Y = piv.columns.values, piv.index.values
        Z    = piv.values
        XX, YY = np.meshgrid(X, Y)

        fig = Figure(figsize=(10, 4.5), facecolor=C["bg"])
        gs  = GridSpec(1, 2, figure=fig, wspace=0.4)

        ax1 = fig.add_subplot(gs[0, 0])
        ax1.set_facecolor(C["panel"])
        ax1.set_title(f"Изолинии T (шаг {step})", color=C["text"], fontsize=10)
        ax1.set_xlabel("x [м]", color=C["text_dim"], fontsize=9)
        ax1.set_ylabel("y [м]", color=C["text_dim"], fontsize=9)
        ax1.tick_params(colors=C["text_dim"], labelsize=8)
        for sp in ax1.spines.values():
            sp.set_color(C["border"])

        T_range = float(Z.max()) - float(Z.min())
        if T_range < 0.01:
            # Поле однородное — заливка + текст вместо изолиний
            ax1.imshow([[float(Z.mean())]], cmap=self._cmap,
                       vmin=float(Z.mean())-1, vmax=float(Z.mean())+1,
                       extent=[0,1,0,1], origin="lower", aspect="equal")
            ax1.text(0.5, 0.5,
                     f"Поле равномерное\nT \u2248 {float(Z.mean()):.2f} \u00b0C",
                     ha="center", va="center", color="white", fontsize=12,
                     transform=ax1.transAxes)
        else:
            cf = ax1.contourf(XX, YY, Z, levels=20, cmap=self._cmap)
            ax1.contour(XX, YY, Z, levels=10, colors="white",
                        linewidths=0.4, alpha=0.4)
            fig.colorbar(cf, ax=ax1, fraction=0.046).ax.tick_params(
                colors=C["text_dim"], labelsize=7)

        ax2 = fig.add_subplot(gs[0, 1], projection="3d")
        ax2.set_facecolor(C["bg"])
        ax2.plot_surface(XX, YY, Z, cmap=self._cmap, linewidth=0, antialiased=True)
        ax2.set_title(f"3D поверхность (шаг {step})",
                      color=C["text"], fontsize=10)
        ax2.set_xlabel("x [м]", color=C["text_dim"], fontsize=8)
        ax2.set_ylabel("y [м]", color=C["text_dim"], fontsize=8)
        ax2.set_zlabel("T [°C]", color=C["text_dim"], fontsize=8)
        ax2.tick_params(colors=C["text_dim"], labelsize=7)
        for pane in [ax2.xaxis.pane, ax2.yaxis.pane, ax2.zaxis.pane]:
            pane.fill = False
            pane.set_edgecolor(C["border"])

        fig.tight_layout(pad=1.5)
        self._embed_fig(self.tab_3d, fig)

    # Вкладка 4 — Профили
    def _draw_profiles(self, out_dir):
        import glob as gl
        files = sorted(gl.glob(os.path.join(out_dir, "slice_z_step*.csv")))
        if not files:
            return

        sel    = [files[0], files[len(files)//2], files[-1]]
        colors = [C["accent"], C["warning"], C["accent2"]]
        labels = ["Начальный", "Промежуточный", "Конечный"]

        fig = Figure(figsize=(10, 5), facecolor=C["bg"])
        gs  = GridSpec(1, 2, figure=fig, wspace=0.4)
        ax_x = fig.add_subplot(gs[0, 0])
        ax_y = fig.add_subplot(gs[0, 1])

        for ax in (ax_x, ax_y):
            self._ax_style(ax)

        for fpath, color, label in zip(sel, colors, labels):
            df   = pd.read_csv(fpath)
            step = int(re.search(r"step(\d+)", fpath).group(1))
            lbl  = f"{label} (шаг {step})"

            px = df[df["y"].between(0.48, 0.52)].sort_values("x")
            py = df[df["x"].between(0.48, 0.52)].sort_values("y")

            if not px.empty:
                ax_x.plot(px["x"], px["T"], color=color, linewidth=2, label=lbl)
                # Min/Max только для последнего шага
                if label == "Конечный":
                    t_min = float(px["T"].min())
                    t_max = float(px["T"].max())
                    x_min = float(px.loc[px["T"].idxmin(), "x"])
                    x_max = float(px.loc[px["T"].idxmax(), "x"])
                    ax_x.scatter([x_min], [t_min], color=C["accent2"],
                                 zorder=5, s=50)
                    ax_x.scatter([x_max], [t_max], color=C["success"],
                                 zorder=5, s=50)
                    ax_x.annotate(f"min={t_min:.1f}°C",
                                  xy=(x_min, t_min),
                                  xytext=(6, 6), textcoords="offset points",
                                  color=C["accent2"], fontsize=8)
                    ax_x.annotate(f"max={t_max:.1f}°C",
                                  xy=(x_max, t_max),
                                  xytext=(6, -14), textcoords="offset points",
                                  color=C["success"], fontsize=8)

            if not py.empty:
                ax_y.plot(py["y"], py["T"], color=color, linewidth=2, label=lbl)
                if label == "Конечный":
                    t_min = float(py["T"].min())
                    t_max = float(py["T"].max())
                    y_min = float(py.loc[py["T"].idxmin(), "y"])
                    y_max = float(py.loc[py["T"].idxmax(), "y"])
                    ax_y.scatter([y_min], [t_min], color=C["accent2"],
                                 zorder=5, s=50)
                    ax_y.scatter([y_max], [t_max], color=C["success"],
                                 zorder=5, s=50)
                    ax_y.annotate(f"min={t_min:.1f}°C",
                                  xy=(y_min, t_min),
                                  xytext=(6, 6), textcoords="offset points",
                                  color=C["accent2"], fontsize=8)
                    ax_y.annotate(f"max={t_max:.1f}°C",
                                  xy=(y_max, t_max),
                                  xytext=(6, -14), textcoords="offset points",
                                  color=C["success"], fontsize=8)

        ax_x.set_xlabel("x [м]", color=C["text_dim"], fontsize=9)
        ax_x.set_ylabel("T [°C]", color=C["text_dim"], fontsize=9)
        ax_x.set_title("Профиль T(x)  при y≈0.5, z=L/2",
                        color=C["text"], fontsize=10)
        ax_x.legend(fontsize=8, facecolor=C["input_bg"],
                    labelcolor=C["text"], edgecolor=C["border"])

        ax_y.set_xlabel("y [м]", color=C["text_dim"], fontsize=9)
        ax_y.set_ylabel("T [°C]", color=C["text_dim"], fontsize=9)
        ax_y.set_title("Профиль T(y)  при x≈0.5, z=L/2",
                        color=C["text"], fontsize=10)
        ax_y.legend(fontsize=8, facecolor=C["input_bg"],
                    labelcolor=C["text"], edgecolor=C["border"])

        fig.tight_layout(pad=1.5)
        self._embed_fig(self.tab_profile, fig)

    def _build_compare_tab(self):
        """Строит вкладку сравнения с кнопками сохранения расчётов A и B."""
        frame = tk.Frame(self.tab_compare, bg=C["bg"])
        frame.pack(fill="both", expand=True)

        # Панель управления
        ctrl = tk.Frame(frame, bg=C["panel"],
                        highlightthickness=1, highlightbackground=C["border"])
        ctrl.pack(fill="x", padx=10, pady=10)

        tk.Label(ctrl, text="СРАВНЕНИЕ РАСЧЁТОВ",
                 font=("Consolas", 9, "bold"),
                 bg=C["panel"], fg=C["text_dim"]).pack(side="left", padx=12, pady=8)

        self.cmp_label_a = tk.StringVar(value="Расчёт A: не сохранён")
        self.cmp_label_b = tk.StringVar(value="Расчёт B: не сохранён")
        self._cmp_data_a = None
        self._cmp_data_b = None

        btn_a = tk.Button(ctrl, text="💾  Сохранить как A",
                          font=("Consolas", 10),
                          bg=C["accent"], fg=C["bg"], relief="flat",
                          activebackground=C["border"],
                          cursor="hand2", padx=10, pady=5,
                          command=self._save_compare_a)
        btn_a.pack(side="left", padx=6, pady=8)

        btn_b = tk.Button(ctrl, text="💾  Сохранить как B",
                          font=("Consolas", 10),
                          bg=C["accent2"], fg=C["bg"], relief="flat",
                          activebackground=C["border"],
                          cursor="hand2", padx=10, pady=5,
                          command=self._save_compare_b)
        btn_b.pack(side="left", padx=6, pady=8)

        btn_cmp = tk.Button(ctrl, text="⚡  Сравнить",
                            font=("Consolas", 10, "bold"),
                            bg=C["btn"], fg="white", relief="flat",
                            activebackground=C["btn_hover"],
                            cursor="hand2", padx=10, pady=5,
                            command=self._draw_compare)
        btn_cmp.pack(side="left", padx=6, pady=8)

        # Статус A и B
        status = tk.Frame(frame, bg=C["bg"])
        status.pack(fill="x", padx=10)

        tk.Label(status, textvariable=self.cmp_label_a,
                 font=("Consolas", 9), bg=C["bg"],
                 fg=C["accent"]).pack(side="left", padx=4)
        tk.Label(status, textvariable=self.cmp_label_b,
                 font=("Consolas", 9), bg=C["bg"],
                 fg=C["accent2"]).pack(side="left", padx=20)

        # Область графиков
        self.tab_compare_plot = tk.Frame(frame, bg=C["bg"])
        self.tab_compare_plot.pack(fill="both", expand=True)
        self._placeholder(self.tab_compare_plot)

    def _load_compare_data(self):
        """Загружает текущие данные из output/."""
        import glob as gl
        hist = os.path.join(self._output_dir, "history.csv")
        z_files = sorted(gl.glob(os.path.join(self._output_dir, "slice_z_step*.csv")))
        if not os.path.exists(hist) or not z_files:
            return None
        df_hist = pd.read_csv(hist)
        df_final = pd.read_csv(z_files[-1])
        params = {
            "material": self.mat_var.get(),
            "alpha": self.alpha_var.get(),
            "t_end": self.t_end_var.get(),
            "t_init": self.t_init_var.get(),
            "nx": self.nx_var.get(),
        }
        return {"hist": df_hist, "final": df_final, "params": params}

    def _save_compare_a(self):
        data = _load_result = self._load_compare_data()
        if data is None:
            messagebox.showwarning("Нет данных",
                "Сначала запустите симуляцию, затем сохраните как A")
            return
        self._cmp_data_a = data
        p = data["params"]
        self.cmp_label_a.set(
            f"A: {p['material']}  α={p['alpha']}  t={p['t_end']}с")

    def _save_compare_b(self):
        data = self._load_compare_data()
        if data is None:
            messagebox.showwarning("Нет данных",
                "Сначала запустите симуляцию, затем сохраните как B")
            return
        self._cmp_data_b = data
        p = data["params"]
        self.cmp_label_b.set(
            f"B: {p['material']}  α={p['alpha']}  t={p['t_end']}с")

    def _draw_compare(self):
        """Рисует сравнение расчётов A и B."""
        if self._cmp_data_a is None or self._cmp_data_b is None:
            messagebox.showwarning("Нет данных",
                "Сохраните оба расчёта (A и B) перед сравнением")
            return

        a = self._cmp_data_a
        b = self._cmp_data_b

        fig = Figure(figsize=(12, 8), facecolor=C["bg"])
        gs  = GridSpec(2, 2, figure=fig, wspace=0.35, hspace=0.45)

        # ── Динамика T_center A vs B ──────────────────────────────────────
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.set_facecolor(C["panel"])
        ax1.plot(a["hist"]["time"], a["hist"]["T_center"],
                 color=C["accent"], linewidth=2,
                 label=f'A: {a["params"]["material"]}')
        ax1.plot(b["hist"]["time"], b["hist"]["T_center"],
                 color=C["accent2"], linewidth=2,
                 label=f'B: {b["params"]["material"]}')
        ax1.set_xlabel("Время [с]", color=C["text_dim"], fontsize=9)
        ax1.set_ylabel("T центра [°C]", color=C["text_dim"], fontsize=9)
        ax1.set_title("T в центре тела", color=C["text"], fontsize=10)
        ax1.legend(fontsize=8, facecolor=C["input_bg"],
                   labelcolor=C["text"], edgecolor=C["border"])
        ax1.tick_params(colors=C["text_dim"], labelsize=8)
        for sp in ax1.spines.values(): sp.set_color(C["border"])
        ax1.grid(color=C["border"], linestyle="--", alpha=0.5)

        # ── Средняя T A vs B ──────────────────────────────────────────────
        ax2 = fig.add_subplot(gs[0, 1])
        ax2.set_facecolor(C["panel"])
        ax2.plot(a["hist"]["time"], a["hist"]["T_mean"],
                 color=C["accent"], linewidth=2,
                 label=f'A: {a["params"]["material"]}')
        ax2.plot(b["hist"]["time"], b["hist"]["T_mean"],
                 color=C["accent2"], linewidth=2,
                 label=f'B: {b["params"]["material"]}')
        ax2.set_xlabel("Время [с]", color=C["text_dim"], fontsize=9)
        ax2.set_ylabel("T средняя [°C]", color=C["text_dim"], fontsize=9)
        ax2.set_title("Средняя T по объёму", color=C["text"], fontsize=10)
        ax2.legend(fontsize=8, facecolor=C["input_bg"],
                   labelcolor=C["text"], edgecolor=C["border"])
        ax2.tick_params(colors=C["text_dim"], labelsize=8)
        for sp in ax2.spines.values(): sp.set_color(C["border"])
        ax2.grid(color=C["border"], linestyle="--", alpha=0.5)

        # ── Тепловая карта A (финал) ──────────────────────────────────────
        all_T = pd.concat([a["final"]["T"], b["final"]["T"]])
        vmin, vmax = float(all_T.min()), float(all_T.max())
        if abs(vmax - vmin) < 0.01:
            vmin -= 1.0; vmax += 1.0

        for n, (data, ax_idx, label, color) in enumerate([
            (a, gs[1, 0], "A", C["accent"]),
            (b, gs[1, 1], "B", C["accent2"]),
        ]):
            piv = data["final"].pivot_table(index="y", columns="x", values="T")
            ax  = fig.add_subplot(ax_idx)
            ax.set_facecolor(C["panel"])
            im = ax.imshow(piv.values, origin="lower", aspect="equal",
                           cmap=self._cmap, vmin=vmin, vmax=vmax,
                           extent=[0,1,0,1])
            p  = data["params"]
            ax.set_title(f"Расчёт {label}: {p['material']}\n"
                         f"α={p['alpha']}  t={p['t_end']}с",
                         color=color, fontsize=9)
            ax.set_xlabel("x [м]", color=C["text_dim"], fontsize=9)
            ax.set_ylabel("y [м]", color=C["text_dim"], fontsize=9)
            ax.tick_params(colors=C["text_dim"], labelsize=7)
            for sp in ax.spines.values(): sp.set_color(C["border"])
            cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cb.ax.tick_params(colors=C["text_dim"], labelsize=7)
            cb.set_label("T [°C]", color=C["text_dim"], fontsize=7)

        fig.tight_layout(pad=1.5)
        self._embed_fig(self.tab_compare_plot, fig)

    # ── Справка ───────────────────────────────────────────────────────────────
    def _show_about(self):
        win = tk.Toplevel(self)
        win.title("О программе — HeatSim 3D")
        win.configure(bg=C["bg"])
        win.geometry("620x580")
        win.resizable(False, False)

        # Заголовок
        tk.Label(win, text="HeatSim 3D",
                 font=("Consolas", 18, "bold"),
                 bg=C["bg"], fg=C["accent"]).pack(pady=(20, 2))
        tk.Label(win, text="Моделирование теплопроводности в сплошных средах",
                 font=("Consolas", 10),
                 bg=C["bg"], fg=C["text_dim"]).pack(pady=(0, 16))

        tk.Frame(win, bg=C["border"], height=1).pack(fill="x", padx=20)

        # Текст справки
        text_frame = tk.Frame(win, bg=C["panel"],
                              highlightthickness=1,
                              highlightbackground=C["border"])
        text_frame.pack(fill="both", expand=True, padx=20, pady=16)

        txt = tk.Text(text_frame, bg=C["panel"], fg=C["text"],
                      font=("Consolas", 10), relief="flat",
                      wrap="word", padx=16, pady=12,
                      state="normal", cursor="arrow")
        txt.pack(fill="both", expand=True)

        sb = ttk.Scrollbar(text_frame, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)

        # Теги форматирования
        txt.tag_configure("h1", font=("Consolas", 12, "bold"),
                          foreground=C["accent"])
        txt.tag_configure("h2", font=("Consolas", 10, "bold"),
                          foreground=C["accent2"])
        txt.tag_configure("eq", font=("Consolas", 11),
                          foreground=C["warning"],
                          background=C["input_bg"])
        txt.tag_configure("dim", foreground=C["text_dim"])

        def h1(t): txt.insert("end", t + "\n", "h1")
        def h2(t): txt.insert("end", t + "\n", "h2")
        def eq(t): txt.insert("end", "  " + t + "\n", "eq")
        def p(t):  txt.insert("end", t + "\n")
        def dim(t): txt.insert("end", t + "\n", "dim")
        def nl():  txt.insert("end", "\n")

        h1("Физическая модель")
        nl()
        p("Программа решает нестационарное уравнение теплопроводности")
        p("(уравнение Фурье–Кирхгофа) в трёхмерной области:")
        nl()
        eq("∂T/∂t = α · (∂²T/∂x² + ∂²T/∂y² + ∂²T/∂z²)")
        nl()
        p("где:")
        dim("  T       — температура [°C]")
        dim("  t       — время [с]")
        dim("  α       — коэффициент температуропроводности [м²/с]")
        dim("  α = λ / (ρ · cₚ),  λ — теплопроводность,")
        dim("                      ρ — плотность,  cₚ — теплоёмкость")
        nl()

        h1("Численный метод")
        nl()
        p("Используется явная конечно-разностная схема FTCS")
        p("(Forward Time, Centered Space):")
        nl()
        eq("T(n+1) = T(n) + rx·δ²xT + ry·δ²yT + rz·δ²zT")
        nl()
        dim("  rx = α·Δt/Δx²,  ry = α·Δt/Δy²,  rz = α·Δt/Δz²")
        nl()
        h2("Условие устойчивости (критерий КФЛ):")
        eq("  2α·Δt·(1/Δx² + 1/Δy² + 1/Δz²) < 1")
        p("Шаг Δt выбирается автоматически с коэффициентом 0.4.")
        nl()

        h1("Расчётная область и условия")
        nl()
        dim("  Область    : прямоугольный параллелепипед (куб по умолчанию)")
        dim("  Сетка      : равномерная декартова Nx × Ny × Nz")
        dim("  НУ         : T(x,y,z,0) = T начальная")
        dim("  ГУ         : условия Дирихле — фиксированная температура")
        dim("               на каждой из 6 граней независимо")
        nl()

        h1("Параметры программы")
        nl()
        dim("  α  (м²/с)     — температуропроводность материала")
        dim("  t_end  (с)    — время моделирования")
        dim("  Nx/Ny/Nz      — число узлов сетки по каждой оси")
        dim("  T начальная   — температура внутри тела в момент t=0")
        dim("  X−/X+/Y−/Y+/Z−/Z+  — температуры на 6 гранях")
        nl()

        h1("Выходные данные")
        nl()
        dim("  Динамика T    — T в центре тела и средняя T по времени")
        dim("  Срезы XY      — тепловые карты плоскости z=L/2")
        dim("  3D+Изолинии   — изолинии и 3D поверхность T(x,y)")
        dim("  Профили       — T(x) и T(y) вдоль центральных осей")

        txt.configure(state="disabled")

        tk.Button(win, text="Закрыть", font=("Consolas", 10),
                  bg=C["btn"], fg="white", relief="flat",
                  activebackground=C["btn_hover"],
                  cursor="hand2", pady=6,
                  command=win.destroy).pack(pady=(0, 16), padx=20, fill="x")

    # ── Закрытие ──────────────────────────────────────────────────────────────

    def _late_init(self):
        if hasattr(self, "_cmap_cb"):
            self._cmap_cb.bind("<<ComboboxSelected>>", self._on_cmap)
        if hasattr(self, "cmap_preview"):
            self._draw_cmap_preview("inferno")

    def _on_cmap(self, _=None):
        name = self.cmap_var.get()
        self._cmap = name
        self._draw_cmap_preview(name)
        if os.path.exists(os.path.join(self._output_dir, "history.csv")):
            self._draw_all(self._output_dir)

    def _draw_cmap_preview(self, name):
        import matplotlib.cm as mcm
        canvas = self.cmap_preview
        canvas.update_idletasks()
        w = canvas.winfo_width()
        if w < 10:
            w = 260
        h = 18
        canvas.delete("all")
        try:
            import matplotlib
            cmap = matplotlib.colormaps[name]
            steps = max(w, 64)
            for i in range(steps):
                r, g, b, _ = cmap(i / steps)
                color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
                x0 = int(i * w / steps)
                x1 = int((i+1) * w / steps) + 1
                canvas.create_rectangle(x0, 0, x1, h,
                                        fill=color, outline="")
        except Exception:
            pass

    def _on_close(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self.destroy()


if __name__ == "__main__":
    app = HeatSimApp()
    app.mainloop()
