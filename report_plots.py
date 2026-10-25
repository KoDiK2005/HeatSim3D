"""
report_plots.py — графики для отчёта/НИР в «журнальном» стиле
===============================================================
Белый фон, чёрные линии, серый пунктир сетки, шрифт с засечками,
рамка легенды в углу, горизонтальная штриховая линия-ориентир
с подписью справа и подпись «Рисунок N — ...» под парой графиков (а), (б).

Использование из командной строки:
    python report_plots.py output                    # все рисунки по результатам расчёта
    python report_plots.py output --num 3.5 --fmt png pdf
    python report_plots.py --bench --exe heat3d.exe --threads 1 2 4 8 --nx 80
                                                     # замер ускорения OpenMP + рисунок

Из GUI: кнопки «Графики для отчёта» и «Замер ускорения OpenMP».
"""

import argparse
import glob
import os
import re
import subprocess
import sys

import numpy as np
import pandas as pd
import matplotlib
from matplotlib.figure import Figure

# ─── Стиль ────────────────────────────────────────────────────────────────────
STYLE = {
    "font.family":        "serif",
    "font.serif":         ["CMU Serif", "Latin Modern Roman", "Times New Roman",
                           "Liberation Serif", "DejaVu Serif"],
    "mathtext.fontset":   "cm",
    "font.size":          13,
    "axes.labelsize":     14,
    "xtick.labelsize":    12,
    "ytick.labelsize":    12,
    "legend.fontsize":    13,
    "axes.edgecolor":     "black",
    "axes.linewidth":     0.8,
    "axes.spines.top":    False,
    "axes.spines.right":  False,
    "axes.grid":          True,
    "grid.color":         "#c8c8c8",
    "grid.linewidth":     0.6,
    "grid.linestyle":     "-",
    "lines.linewidth":    1.3,
    "lines.color":        "black",
    "xtick.direction":    "out",
    "ytick.direction":    "out",
    "legend.frameon":     True,
    "legend.fancybox":    False,
    "legend.edgecolor":   "black",
    "legend.framealpha":  1.0,
    "figure.facecolor":   "white",
    "axes.facecolor":     "white",
    "savefig.facecolor":  "white",
    "savefig.dpi":        300,
}

# Чёрно-белые варианты линий для нескольких кривых на одной оси
LINESTYLES = ["-", "--", "-.", ":"]
GRAYS      = ["black", "#555555", "#888888", "#aaaaaa"]


def _style():
    return matplotlib.rc_context(STYLE)


def _ref_line(ax, y, label):
    """Горизонтальная штриховая линия-ориентир с подписью справа от оси."""
    ax.axhline(y, color="black", linestyle=(0, (6, 4)), linewidth=1.0)
    ax.annotate(label, xy=(1.0, y), xycoords=("axes fraction", "data"),
                xytext=(6, 0), textcoords="offset points",
                va="center", ha="left", fontsize=14, fontweight="bold",
                annotation_clip=False)


def _panel(ax, x, y, xlabel, ylabel, legend=None, ref=None, series=None):
    """
    Одна панель: кривая (или несколько series=[(x, y, label), ...]),
    подписи осей, легенда в рамке сверху справа, линия-ориентир ref=(y, label).
    """
    if series is None:
        series = [(x, y, legend)]
    for n, (sx, sy, lbl) in enumerate(series):
        ax.plot(sx, sy, color=GRAYS[n % 4], linestyle=LINESTYLES[n % 4],
                label=lbl)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.margins(x=0.02)
    if any(lbl for _, _, lbl in series):
        ax.legend(loc="best", handlelength=1.6, borderpad=0.3)
    if ref is not None:
        _ref_line(ax, *ref)


def figure_pair(left, right, caption, num=None, out_path=None, fmts=("png",),
                xticks=None):
    """
    Пара графиков (а) и (б) с общей подписью «Рисунок N — caption».
    left / right — словари аргументов для _panel().
    Возвращает список сохранённых файлов (или Figure, если out_path=None).
    """
    with _style():
        fig = Figure(figsize=(10, 5.2))
        axes = fig.subplots(1, 2)
        fig.subplots_adjust(left=0.09, right=0.9, wspace=0.42,
                            top=0.95, bottom=0.27)
        for ax, spec in zip(axes, (left, right)):
            _panel(ax, **spec)
            if xticks is not None:
                ax.set_xticks(list(xticks))
        title = f"Рисунок {num} — {caption}" if num else caption
        fig.text(0.5, 0.04, title, ha="center", va="bottom", fontsize=15,
                 wrap=True)
        if out_path is None:
            return fig
        saved = []
        for ext in fmts:
            path = f"{out_path}.{ext}"
            fig.savefig(path, bbox_inches="tight")
            saved.append(path)
        return saved


# ─── Чтение результатов расчёта ───────────────────────────────────────────────
def read_params(out_dir):
    path = os.path.join(out_dir, "params.csv")
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    return dict(zip(df["key"], df["value"].astype(float)))


def _bc_list(prm):
    keys = ["t_xm", "t_xp", "t_ym", "t_yp", "t_zm", "t_zp"]
    return [prm[k] for k in keys if k in prm]


def _steps(out_dir, axis):
    files = glob.glob(os.path.join(out_dir, f"slice_{axis}_step*.csv"))
    return sorted(files, key=lambda f: int(re.search(r"step(\d+)", f).group(1)))


def _time_unit(t_max):
    """Подбор единиц времени, чтобы на оси не было 6-значных чисел."""
    if t_max >= 3 * 86400:
        return 86400.0, "сут"
    if t_max >= 3 * 3600:
        return 3600.0, "ч"
    if t_max >= 300:
        return 60.0, "мин"
    return 1.0, "с"


def _profile(df, coord, other):
    """Профиль T вдоль coord по середине по второй координате."""
    mid = df[other].unique()
    mid = mid[np.argmin(np.abs(mid - (mid.min() + mid.max()) / 2))]
    return df[np.isclose(df[other], mid)].sort_values(coord)


# ─── Рисунки ──────────────────────────────────────────────────────────────────
def fig_history(out_dir, save_to, num=None, fmts=("png",)):
    df  = pd.read_csv(os.path.join(out_dir, "history.csv"))
    prm = read_params(out_dir)
    scale, unit = _time_unit(float(df["time"].max()))
    t = df["time"] / scale

    ref = None
    bc = _bc_list(prm)
    if bc:
        # Установившаяся температура при одинаковых гранях = T граней,
        # иначе ориентир — средняя по граням
        ref = (float(np.mean(bc)), r"$\mathbb{T}$гр")

    return figure_pair(
        dict(x=t, y=df["T_center"], legend=r"$T_c$",
             xlabel=f"t ({unit})", ylabel="T, °C", ref=ref),
        dict(x=t, y=df["T_mean"], legend=r"$\langle T \rangle$",
             xlabel=f"t ({unit})", ylabel="T, °C", ref=ref),
        "Температура в центре тела (а) и средняя\n"
        "температура по объёму (б) в процессе нагрева.",
        num, os.path.join(save_to, "fig_history"), fmts)


def fig_profiles(out_dir, save_to, num=None, fmts=("png",)):
    files = _steps(out_dir, "z")
    if not files:
        return []
    hist = pd.read_csv(os.path.join(out_dir, "history.csv"))
    step2time = dict(zip(hist["step"], hist["time"]))
    scale, unit = _time_unit(float(hist["time"].max()))

    pick = sorted({0, len(files) // 4, len(files) // 2, len(files) - 1})
    sx, sy = [], []
    for n in pick:
        df   = pd.read_csv(files[n])
        step = int(re.search(r"step(\d+)", files[n]).group(1))
        lbl  = f"t = {step2time.get(step, 0) / scale:.4g} {unit}"
        px, py = _profile(df, "x", "y"), _profile(df, "y", "x")
        sx.append((px["x"], px["T"], lbl))
        sy.append((py["y"], py["T"], lbl))

    return figure_pair(
        dict(x=None, y=None, series=sx, xlabel="x, м", ylabel="T, °C"),
        dict(x=None, y=None, series=sy, xlabel="y, м", ylabel="T, °C"),
        "Профили температуры T(x) при y = L/2 (а)\n"
        "и T(y) при x = L/2 (б) в сечении z = L/2.",
        num, os.path.join(save_to, "fig_profiles"), fmts)


def fig_speedup(bench_csv, save_to, num=None, fmts=("png",)):
    df = pd.read_csv(bench_csv)
    p  = df["threads"]
    return figure_pair(
        dict(x=p, y=df["time"], legend=r"$t_p$",
             xlabel="число потоков p", ylabel="время расчёта, с"),
        dict(x=None, y=None, xlabel="число потоков p",
             ylabel=r"ускорение $S_p = t_1 / t_p$",
             series=[(p, df["speedup"], r"$S_p$"),
                     (p, p, r"$S_p = p$")]),
        "Время расчёта (а) и ускорение (б) параллельной\n"
        "OpenMP-версии программы в зависимости от числа потоков.",
        num, os.path.join(save_to, "fig_speedup"), fmts, xticks=p)


def make_all(out_dir, save_to=None, num_start=None, fmts=("png",)):
    """Все рисунки по результатам расчёта. num_start='3.5' → 3.5, 3.6, ..."""
    save_to = save_to or os.path.join(out_dir, "report")
    os.makedirs(save_to, exist_ok=True)

    def num(i):
        if not num_start:
            return None
        head, _, tail = str(num_start).rpartition(".")
        return f"{head}.{int(tail) + i}" if head else str(int(tail) + i)

    saved = fig_history(out_dir, save_to, num(0), fmts)
    saved += fig_profiles(out_dir, save_to, num(1), fmts)
    bench = os.path.join(out_dir, "benchmark.csv")
    if os.path.exists(bench):
        saved += fig_speedup(bench, save_to, num(2), fmts)
    return saved


# ─── Замер ускорения OpenMP ──────────────────────────────────────────────────
def run_benchmark(exe, threads, sim_args, workdir, log=print):
    """
    Запускает heat3d с разным числом потоков, пишет benchmark.csv
    (threads,time,speedup,efficiency) в workdir/output и возвращает его путь.
    """
    os.makedirs(workdir, exist_ok=True)
    rows = []
    for p in threads:
        cmd = [exe, *sim_args, "--threads", str(p)]
        res = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        m = re.search(r"Simulation done in\s*([\d.]+)", res.stdout)
        if res.returncode != 0 or not m:
            raise RuntimeError(f"heat3d завершился с ошибкой при p={p}:\n"
                               f"{res.stdout[-500:]}")
        mt = re.search(r"Threads\s*:\s*(\d+)", res.stdout)
        real = int(mt.group(1)) if mt else 1
        if real != p:
            log(f"  [!] запрошено {p} потоков, работало {real} "
                f"(программа собрана без OpenMP?)")
        rows.append((p, float(m.group(1))))
        log(f"  p = {p:3d}   t = {rows[-1][1]:.3f} с")

    df = pd.DataFrame(rows, columns=["threads", "time"])
    df["speedup"]    = df["time"].iloc[0] / df["time"]
    df["efficiency"] = df["speedup"] / df["threads"]
    path = os.path.join(workdir, "output", "benchmark.csv")
    df.to_csv(path, index=False, float_format="%.4f")
    return path


def default_threads():
    n = os.cpu_count() or 1
    ps = [1]
    while ps[-1] * 2 <= n:
        ps.append(ps[-1] * 2)
    if ps[-1] != n:
        ps.append(n)
    return ps


def main(argv=None):
    ap = argparse.ArgumentParser(description="Графики для отчёта HeatSim3D")
    ap.add_argument("out_dir", nargs="?", default="output",
                    help="папка с результатами heat3d (по умолчанию output)")
    ap.add_argument("--save-to", help="куда сохранить (по умолчанию out_dir/report)")
    ap.add_argument("--num", help="номер первого рисунка, напр. 3.5")
    ap.add_argument("--fmt", nargs="+", default=["png"],
                    help="форматы: png pdf svg")
    ap.add_argument("--bench", action="store_true",
                    help="замерить ускорение OpenMP и построить рисунок")
    ap.add_argument("--exe", default="heat3d.exe", help="путь к heat3d")
    ap.add_argument("--threads", nargs="+", type=int,
                    help="число потоков, по умолчанию 1 2 4 ... до числа ядер")
    ap.add_argument("--nx", type=int, default=80, help="размер сетки для замера")
    ap.add_argument("--t_end", type=float, default=20000)
    a = ap.parse_args(argv)

    if a.bench:
        exe = os.path.abspath(a.exe)
        n = str(a.nx)
        sim = ["--nx", n, "--ny", n, "--nz", n, "--t_end", str(a.t_end),
               "--save_every", "1000000000"]
        bench = run_benchmark(exe, a.threads or default_threads(), sim,
                              os.path.join(os.path.dirname(exe), "bench"))
        save_to = a.save_to or os.path.join(os.path.dirname(bench), "report")
        os.makedirs(save_to, exist_ok=True)
        saved = fig_speedup(bench, save_to, a.num, a.fmt)
    else:
        if not os.path.exists(os.path.join(a.out_dir, "history.csv")):
            sys.exit(f"Нет {a.out_dir}/history.csv — сначала запустите расчёт.")
        saved = make_all(a.out_dir, a.save_to, a.num, a.fmt)

    for s in saved:
        print("  сохранено:", s)


if __name__ == "__main__":
    main()
