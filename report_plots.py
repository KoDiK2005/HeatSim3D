"""
report_plots.py — графики для отчёта/НИР в «журнальном» стиле
===============================================================
Белый фон, чёрные линии, серый пунктир сетки, шрифт с засечками,
рамка легенды в углу, горизонтальная штриховая линия-ориентир
с подписью справа и подпись «Рисунок N — ...» под парой графиков (а), (б).

Использование из командной строки:
    python report_plots.py output                    # все рисунки по результатам расчёта
    python report_plots.py output --num 3.5 --fmt png pdf
    python report_plots.py --bench --threads 1 2 4 8 --nx 50 100 150
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
from matplotlib.ticker import FuncFormatter

# Расчётное ядро: heat3d на Linux/macOS, heat3d.exe на Windows
ENGINE = "heat3d.exe" if os.name == "nt" else "heat3d"

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
MARKERS    = ["o", "s", "^", "D"]


# Режим «для LaTeX»: рисунок вставляется в отчёт в натуральную величину
# (\includegraphics без масштабирования), поэтому шрифт на рисунке совпадает
# с основным текстом по размеру; подпись «Рисунок N — ...» ставит сам LaTeX,
# а под каждой панелью пишется «а)», «б)».
LATEX = None


def set_latex_mode(width_in=6.5, height_in=3.2, font_pt=14):
    global LATEX
    LATEX = dict(size=(width_in, height_in), pt=font_pt)


def _style():
    st = dict(STYLE)
    if LATEX:
        pt = LATEX["pt"]
        st.update({"font.size": pt, "axes.labelsize": pt,
                   "xtick.labelsize": pt, "ytick.labelsize": pt,
                   "legend.fontsize": pt, "lines.linewidth": 1.0,
                   "axes.linewidth": 0.6, "grid.linewidth": 0.4})
    return matplotlib.rc_context(st)


def _ref_line(ax, y, label):
    """Горизонтальная штриховая линия-ориентир с подписью справа от оси."""
    ax.axhline(y, color="black", linestyle=(0, (6, 4)), linewidth=1.0)
    ax.annotate(label, xy=(1.0, y), xycoords=("axes fraction", "data"),
                xytext=(6, 0), textcoords="offset points",
                va="center", ha="left", fontsize=14, fontweight="bold",
                annotation_clip=False)


def _panel(ax, x, y, xlabel, ylabel, legend=None, ref=None, series=None,
           legend_loc="best"):
    """
    Одна панель: кривая (или несколько series=[(x, y, label), ...]),
    подписи осей, легенда в рамке сверху справа, линия-ориентир ref=(y, label).
    """
    if series is None:
        series = [(x, y, legend)]
    for n, (sx, sy, lbl) in enumerate(series):
        few = len(sx) <= 12          # мало точек (замеры) — отмечаем маркерами
        ax.plot(sx, sy, color=GRAYS[n % 4], linestyle=LINESTYLES[n % 4],
                marker=MARKERS[n % 4] if few else None, markersize=5,
                markerfacecolor="white", label=lbl)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.margins(x=0.02)
    if any(lbl for _, _, lbl in series):
        ax.legend(loc=legend_loc, handlelength=1.6, borderpad=0.3)
    if ref is not None:
        _ref_line(ax, *ref)


def figure_pair(left, right, caption, num=None, out_path=None, fmts=("png",),
                xticks=None, legend_top=False):
    """
    Пара графиков (а) и (б) с общей подписью «Рисунок N — caption».
    left / right — словари аргументов для _panel().
    Возвращает список сохранённых файлов (или Figure, если out_path=None).
    """
    with _style():
        fig = Figure(figsize=LATEX["size"] if LATEX else (10, 5.2))
        axes = fig.subplots(1, 2)
        if LATEX:
            fig.subplots_adjust(wspace=0.45)
        else:
            fig.subplots_adjust(left=0.09, right=0.9, wspace=0.42,
                                top=0.95, bottom=0.27)
        for n, (ax, spec) in enumerate(zip(axes, (left, right))):
            _panel(ax, **spec)
            if xticks is not None:
                ax.set_xticks(list(xticks))
            if LATEX:
                ax.set_xlabel(ax.get_xlabel() + "\n" + "аб"[n] + ")")
                # десятичная запятая, как в тексте отчёта
                comma = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))
                ax.xaxis.set_major_formatter(comma)
                ax.yaxis.set_major_formatter(comma)
        if legend_top and LATEX:
            # Общая легенда над панелями — не закрывает кривые
            src = max(axes, key=lambda a: len(a.get_lines()))
            handles, labels = src.get_legend_handles_labels()
            for ax in axes:
                if ax.get_legend():
                    ax.get_legend().remove()
            fig.legend(handles, labels, loc="lower center", ncol=len(labels),
                       bbox_to_anchor=(0.5, 0.97), handlelength=1.8,
                       columnspacing=1.0, borderpad=0.3)
        if not LATEX:
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
    out = os.path.join(save_to, "fig_speedup")

    if "nx" in df and df["nx"].nunique() > 1:
        # Несколько сеток: ускорение (а) и эффективность (б) для каждой N³
        p = sorted(df["threads"].unique())
        sp, ep = [], []
        for nx, g in df.groupby("nx"):
            lbl = rf"$N = {nx}^3$"
            sp.append((g["threads"], g["speedup"], lbl))
            ep.append((g["threads"], g["efficiency"], lbl))
        sp.append((p, p, r"$S_p = p$"))
        return figure_pair(
            dict(x=None, y=None, series=sp, xlabel="число потоков $p$",
                 ylabel=r"ускорение $S_p = t_1 / t_p$"),
            dict(x=None, y=None, series=ep, xlabel="число потоков $p$",
                 ylabel=r"эффективность $E_p = S_p / p$", ref=(1.0, "")),
            "Ускорение (а) и эффективность (б) параллельной OpenMP-версии\n"
            "программы для расчётных сеток разного размера.",
            num, out, fmts, xticks=p, legend_top=True)

    p = df["threads"]
    return figure_pair(
        dict(x=p, y=df["time"], legend=r"$t_p$",
             xlabel="число потоков $p$", ylabel="время расчёта, с"),
        dict(x=None, y=None, xlabel="число потоков $p$",
             ylabel=r"ускорение $S_p = t_1 / t_p$",
             series=[(p, df["speedup"], r"$S_p$"),
                     (p, p, r"$S_p = p$")]),
        "Время расчёта (а) и ускорение (б) параллельной\n"
        "OpenMP-версии программы в зависимости от числа потоков.",
        num, out, fmts, xticks=p)


def analytic_center(t, alpha, t0, tb, terms=41):
    """
    Аналитическое решение в центре единичного куба (все грани tb, начальная t0):
    T = tb + (t0 - tb) Σ 64/(π³lmn) sin(lπ/2) sin(mπ/2) sin(nπ/2)
                       · exp(-απ²(l²+m²+n²)t),  l, m, n — нечётные.
    """
    k = np.arange(1, terms, 2)
    sk = (-1.0) ** ((k - 1) // 2) / k                 # sin(kπ/2)/k
    lam = np.pi ** 2 * k ** 2
    t = np.asarray(t, dtype=float)[:, None]
    f = (sk * np.exp(-alpha * lam * t))               # (len(t), len(k))
    s = 64 / np.pi ** 3 * f.sum(axis=1) ** 3          # ряд распадается на 3 множителя
    return tb + (t0 - tb) * s


def fig_validation(out_dir, save_to, num=None, fmts=("png",)):
    """Сравнение с аналитикой — только для одинаковых температур граней."""
    prm = read_params(out_dir)
    bc = _bc_list(prm)
    if len(bc) != 6 or len(set(bc)) != 1 or "alpha" not in prm:
        return []
    df = pd.read_csv(os.path.join(out_dir, "history.csv"))
    df = df[df["time"] > 0]
    exact = analytic_center(df["time"], prm["alpha"], prm["t_init"], bc[0])
    scale, unit = _time_unit(float(df["time"].max()))
    t = df["time"] / scale
    return figure_pair(
        dict(x=None, y=None, xlabel=f"t ({unit})", ylabel="T, °C",
             series=[(t, df["T_center"], "численное"),
                     (t, exact, "аналитическое")]),
        dict(x=t, y=np.abs(df["T_center"] - exact), legend=r"$|T_c - T_{ан}|$",
             xlabel=f"t ({unit})", ylabel="абсолютная погрешность, °C"),
        "Температура в центре куба: численное и аналитическое\n"
        "решения (а) и абсолютная погрешность (б).",
        num, os.path.join(save_to, "fig_validation"), fmts)


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
    k = 2
    val = fig_validation(out_dir, save_to, num(k), fmts)
    if val:
        saved += val
        k += 1
    bench = os.path.join(out_dir, "benchmark.csv")
    if os.path.exists(bench):
        saved += fig_speedup(bench, save_to, num(k), fmts)
    return saved


# ─── Замер ускорения OpenMP ──────────────────────────────────────────────────
def _bench_rows(exe, threads, sim_args, workdir, log, repeat):
    """Время расчёта для каждого числа потоков (минимум из repeat запусков)."""
    rows = []
    for p in threads:
        best = None
        for _ in range(max(1, repeat)):
            cmd = [exe, *sim_args, "--threads", str(p)]
            res = subprocess.run(cmd, cwd=workdir, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace")
            m = re.search(r"Simulation done in\s*([\d.]+)", res.stdout)
            if res.returncode != 0 or not m:
                raise RuntimeError(f"heat3d завершился с ошибкой при p={p}:\n"
                                   f"{res.stdout[-500:]}")
            mt = re.search(r"Threads\s*:\s*(\d+)", res.stdout)
            real = int(mt.group(1)) if mt else 1
            if real != p:
                log(f"  [!] запрошено {p} потоков, работало {real} "
                    f"(программа собрана без OpenMP?)")
            t = float(m.group(1))
            best = t if best is None else min(best, t)
        rows.append((p, best))
        log(f"  p = {p:3d}   t = {best:.3f} с")
    return rows


def _with_speedup(df):
    t1 = df["time"].iloc[0]
    df["speedup"]    = t1 / df["time"]
    df["efficiency"] = df["speedup"] / df["threads"]
    return df


def run_benchmark(exe, threads, sim_args, workdir, log=print, repeat=1):
    """
    Запускает heat3d с разным числом потоков, пишет benchmark.csv
    (threads,time,speedup,efficiency) в workdir/output и возвращает его путь.
    """
    os.makedirs(os.path.join(workdir, "output"), exist_ok=True)
    rows = _bench_rows(exe, threads, sim_args, workdir, log, repeat)
    df = _with_speedup(pd.DataFrame(rows, columns=["threads", "time"]))
    path = os.path.join(workdir, "output", "benchmark.csv")
    df.to_csv(path, index=False, float_format="%.4f")
    return path


def run_scaling(exe, sizes, threads, steps, workdir, log=print, repeat=1,
                alpha=1.28e-5):
    """
    Замер на нескольких сетках N×N×N с одинаковым числом шагов по времени.
    Пишет benchmark.csv (nx,threads,time,speedup,efficiency).
    """
    os.makedirs(os.path.join(workdir, "output"), exist_ok=True)
    parts = []
    for nx in sizes:
        dx = 1.0 / (nx - 1)
        dt = 0.4 / (2.0 * alpha * 3.0 / (dx * dx))     # как computeStableDt()
        sim = ["--nx", str(nx), "--ny", str(nx), "--nz", str(nx),
               "--alpha", f"{alpha:.6e}", "--t_end", f"{steps * dt:.6f}",
               "--save_every", "1000000000"]
        log(f"Сетка {nx}^3, {steps} шагов:")
        rows = _bench_rows(exe, threads, sim, workdir, log, repeat)
        df = _with_speedup(pd.DataFrame(rows, columns=["threads", "time"]))
        df.insert(0, "nx", nx)
        parts.append(df)
    path = os.path.join(workdir, "output", "benchmark.csv")
    pd.concat(parts).to_csv(path, index=False, float_format="%.4f")
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
    ap.add_argument("--exe", default=ENGINE, help="путь к heat3d")
    ap.add_argument("--threads", nargs="+", type=int,
                    help="число потоков, по умолчанию 1 2 4 ... до числа ядер")
    ap.add_argument("--nx", type=int, nargs="+", default=[80],
                    help="размер сетки N (N×N×N); несколько — сравнение сеток")
    ap.add_argument("--steps", type=int, default=300,
                    help="число шагов по времени в каждом замере")
    ap.add_argument("--repeat", type=int, default=3,
                    help="повторов на точку (берётся минимальное время)")
    a = ap.parse_args(argv)

    if a.bench:
        exe = os.path.abspath(a.exe)
        bench = run_scaling(exe, a.nx, a.threads or default_threads(), a.steps,
                            os.path.join(os.path.dirname(exe), "bench"),
                            repeat=a.repeat)
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
