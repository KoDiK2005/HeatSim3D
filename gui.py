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
    "Алюминий":                8.42e-5,
    "Медь":                    1.17e-4,
    "Бетон":                   5.71e-7,
    "Дерево (дуб)":            1.60e-7,
    "Вода":                    1.43e-7,
    "Воздух":                  2.11e-5,
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
        self._output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "output")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")

        main = tk.Frame(self, bg=C["bg"])
        main.pack(fill="both", expand=True, padx=20, pady=12)

        # Левая панель
        left = tk.Frame(main, bg=C["panel"], bd=0,
                        highlightthickness=1, highlightbackground=C["border"],
                        width=310)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)
        self._build_params(left)

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
        self._section(parent, "Температурные условия (°C)")
        self.t_init_var = self._entry_row(
            parent, "T начальная", "20",
            "Начальная температура внутри тела")
        self.t_bnd_var = self._entry_row(
            parent, "T граница", "100",
            "Температура Дирихле на всех гранях")

        # Частота сохранения
        self._section(parent, "Частота сохранения")
        self.save_var = self._entry_row(
            parent, "Каждые N шагов", "500",
            "Как часто сохранять срезы в CSV")

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

        nb.add(self.tab_history, text="  Динамика T  ")
        nb.add(self.tab_slices,  text="  Срезы XY  ")
        nb.add(self.tab_3d,      text="  3D + Изолинии  ")
        nb.add(self.tab_profile, text="  Профили  ")

        for tab in [self.tab_history, self.tab_slices,
                    self.tab_3d, self.tab_profile]:
            self._placeholder(tab)

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
            return {
                "nx":         int(self.nx_var.get()),
                "ny":         int(self.ny_var.get()),
                "nz":         int(self.nz_var.get()),
                "alpha":      float(self.alpha_var.get()),
                "t_end":      float(self.t_end_var.get()),
                "t_init":     float(self.t_init_var.get()),
                "t_boundary": float(self.t_bnd_var.get()),
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
            "--t_boundary", str(p["t_boundary"]),
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
        for w in tab.winfo_children():
            w.destroy()
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

        fig = Figure(figsize=(10, 4.5), facecolor=C["bg"])
        gs  = GridSpec(1, 2, figure=fig, wspace=0.35)

        for i, (col, label, color) in enumerate([
            ("T_center", "Температура в центре [°C]", C["accent2"]),
            ("T_mean",   "Средняя температура [°C]",  C["accent"]),
        ]):
            ax = fig.add_subplot(gs[0, i])
            self._ax_style(ax)
            ax.plot(df["time"], df[col], color=color, linewidth=2)
            ax.fill_between(df["time"], df[col], alpha=0.12, color=color)
            ax.set_xlabel("Время [с]", color=C["text_dim"], fontsize=9)
            ax.set_ylabel(label, color=C["text_dim"], fontsize=9)
            ax.set_title(label, color=C["text"], fontsize=10)

        self._embed_fig(self.tab_history, fig)

    # Вкладка 2 — Срезы XY
    def _draw_slices(self, out_dir):
        files = sorted(glob.glob(os.path.join(out_dir, "slice_z_step*.csv")))
        if not files:
            return
        idxs = np.linspace(0, len(files)-1, min(6, len(files)), dtype=int)
        sel  = [files[i] for i in idxs]

        all_T = pd.concat([pd.read_csv(f)["T"] for f in sel])
        vmin, vmax = all_T.min(), all_T.max()

        rows = 2 if len(sel) > 3 else 1
        cols = (len(sel) + rows - 1) // rows
        fig  = Figure(figsize=(10, 4.5 * rows), facecolor=C["bg"])

        for n, fpath in enumerate(sel):
            df   = pd.read_csv(fpath)
            step = int(re.search(r"step(\d+)", fpath).group(1))
            piv  = df.pivot_table(index="y", columns="x", values="T")

            ax = fig.add_subplot(rows, cols, n + 1)
            ax.set_facecolor(C["panel"])
            im = ax.imshow(piv.values, origin="lower", aspect="equal",
                           cmap=CMAP, vmin=vmin, vmax=vmax, extent=[0,1,0,1])
            ax.set_title(f"Шаг {step}", color=C["text"], fontsize=9)
            ax.tick_params(colors=C["text_dim"], labelsize=7)
            for sp in ax.spines.values():
                sp.set_color(C["border"])
            cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cb.ax.tick_params(colors=C["text_dim"], labelsize=7)

        fig.tight_layout(pad=1.5)
        self._embed_fig(self.tab_slices, fig)

    # Вкладка 3 — 3D + изолинии
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
        cf = ax1.contourf(XX, YY, Z, levels=20, cmap=CMAP)
        ax1.contour(XX, YY, Z, levels=10, colors="white",
                    linewidths=0.4, alpha=0.4)
        ax1.set_title(f"Изолинии T (шаг {step})", color=C["text"], fontsize=10)
        ax1.set_xlabel("x [м]", color=C["text_dim"], fontsize=9)
        ax1.set_ylabel("y [м]", color=C["text_dim"], fontsize=9)
        ax1.tick_params(colors=C["text_dim"], labelsize=8)
        for sp in ax1.spines.values():
            sp.set_color(C["border"])
        fig.colorbar(cf, ax=ax1, fraction=0.046).ax.tick_params(
            colors=C["text_dim"], labelsize=7)

        ax2 = fig.add_subplot(gs[0, 1], projection="3d")
        ax2.set_facecolor(C["bg"])
        ax2.plot_surface(XX, YY, Z, cmap=CMAP, linewidth=0, antialiased=True)
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
        files = sorted(glob.glob(os.path.join(out_dir, "slice_z_step*.csv")))
        if not files:
            return

        sel    = [files[0], files[len(files)//2], files[-1]]
        colors = [C["accent"], C["warning"], C["accent2"]]
        labels = ["Начальный", "Промежуточный", "Конечный"]

        fig = Figure(figsize=(10, 4.5), facecolor=C["bg"])
        gs  = GridSpec(1, 2, figure=fig, wspace=0.35)
        ax_x = fig.add_subplot(gs[0, 0])
        ax_y = fig.add_subplot(gs[0, 1])

        for ax in (ax_x, ax_y):
            self._ax_style(ax)

        for fpath, color, label in zip(sel, colors, labels):
            df   = pd.read_csv(fpath)
            step = int(re.search(r"step(\d+)", fpath).group(1))
            lbl  = f"{label} (шаг {step})"

            px = df[df["y"].between(0.48, 0.52)].sort_values("x")
            ax_x.plot(px["x"], px["T"], color=color, linewidth=2, label=lbl)

            py = df[df["x"].between(0.48, 0.52)].sort_values("y")
            ax_y.plot(py["y"], py["T"], color=color, linewidth=2, label=lbl)

        ax_x.set_xlabel("x [м]", color=C["text_dim"], fontsize=9)
        ax_x.set_ylabel("T [°C]", color=C["text_dim"], fontsize=9)
        ax_x.set_title("Профиль T(x) при y≈0.5", color=C["text"], fontsize=10)
        ax_x.legend(fontsize=8, facecolor=C["input_bg"],
                    labelcolor=C["text"], edgecolor=C["border"])

        ax_y.set_xlabel("y [м]", color=C["text_dim"], fontsize=9)
        ax_y.set_ylabel("T [°C]", color=C["text_dim"], fontsize=9)
        ax_y.set_title("Профиль T(y) при x≈0.5", color=C["text"], fontsize=10)
        ax_y.legend(fontsize=8, facecolor=C["input_bg"],
                    labelcolor=C["text"], edgecolor=C["border"])

        fig.tight_layout(pad=1.5)
        self._embed_fig(self.tab_profile, fig)

    # ── Закрытие ──────────────────────────────────────────────────────────────
    def _on_close(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self.destroy()


if __name__ == "__main__":
    app = HeatSimApp()
    app.mainloop()
