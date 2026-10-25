"""
experiments.py — вычислительные эксперименты и рисунки для отчёта НИР (7 семестр)
=================================================================================
Запуск из корня проекта:
    python nir_7sem/experiments.py            # все эксперименты + рисунки
    python nir_7sem/experiments.py --figs     # только перерисовать по готовым данным

Результаты:
    nir_7sem/data/*.csv  — исходные данные замеров
    nir_7sem/fig/*.pdf   — рисунки для LaTeX (шрифт 14 pt, как в тексте отчёта)
"""
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import report_plots as rp  # noqa: E402

DATA = os.path.join(HERE, "data")
FIG  = os.path.join(HERE, "fig")
EXE  = os.path.join(ROOT, rp.ENGINE)
ALPHA = 1.28e-5


def run(args, workdir):
    out = subprocess.run([EXE, *args], cwd=workdir, capture_output=True,
                         text=True, check=True).stdout
    return float(re.search(r"Simulation done in\s*([\d.]+)", out).group(1))


def best_of(args, workdir, repeat=5):
    return min(run(args, workdir) for _ in range(repeat))


def cube(n):
    return ["--nx", str(n), "--ny", str(n), "--nz", str(n)]


def t_end_for(n, steps):
    dx = 1.0 / (n - 1)
    return steps * 0.4 / (2.0 * ALPHA * 3.0 / (dx * dx))


# ─── 1. Верификация по аналитическому решению ────────────────────────────────
def exp_validation(tmp):
    d = os.path.join(tmp, "val")
    os.makedirs(d)
    run([*cube(31), "--t_end", "20000", "--t_init", "20",
         *sum([[f"--t_{f}", "100"] for f in
               ("xm", "xp", "ym", "yp", "zm", "zp")], []),
         "--save_every", "20"], d)
    h = pd.read_csv(os.path.join(d, "output", "history.csv"))
    h.to_csv(os.path.join(DATA, "validation_history.csv"), index=False)


# ─── 2. Сходимость по сетке ──────────────────────────────────────────────────
def exp_convergence(tmp, t_check=4000.0):
    rows = []
    for n in (11, 21, 41, 81):
        d = os.path.join(tmp, f"conv{n}")
        os.makedirs(d)
        run([*cube(n), "--t_end", "5000", "--t_init", "20",
             "--save_every", "1"], d)
        h = pd.read_csv(os.path.join(d, "output", "history.csv"))
        tc = float(np.interp(t_check, h["time"], h["T_center"]))
        ex = float(rp.analytic_center([t_check], ALPHA, 20, 100)[0])
        rows.append((n, 1.0 / (n - 1), tc, ex, abs(tc - ex)))
    df = pd.DataFrame(rows, columns=["n", "h", "T_num", "T_exact", "err"])
    df["ratio"] = df["err"].shift(1) / df["err"]
    df.to_csv(os.path.join(DATA, "convergence.csv"), index=False,
              float_format="%.5f")


# ─── 3. Масштабируемость ─────────────────────────────────────────────────────
def exp_scaling(tmp):
    path = rp.run_scaling(EXE, [50, 100, 150], [1, 2, 3, 4], 1000,
                          os.path.join(tmp, "bench"), repeat=5)
    pd.read_csv(path).to_csv(os.path.join(DATA, "benchmark.csv"), index=False,
                             float_format="%.4f")


# ─── 4. Влияние последовательной записи результатов ──────────────────────────
def exp_io(tmp, n=100, steps=1000):
    d = os.path.join(tmp, "io")
    os.makedirs(d)
    rows = []
    for writes in (0, 5, 10, 20, 50, 100):
        every = steps // writes if writes else 10 ** 9
        args = [*cube(n), "--t_end", f"{t_end_for(n, steps):.6f}",
                "--save_every", str(every)]
        t1 = best_of([*args, "--threads", "1"], d, 3)
        t4 = best_of([*args, "--threads", "4"], d, 3)
        rows.append((writes, t1, t4))
        print(f"  записей {writes:3d}: t1 = {t1:.3f} с, t4 = {t4:.3f} с")
    df = pd.DataFrame(rows, columns=["writes", "t1", "t4"])
    df["speedup"] = df["t1"] / df["t4"]
    df.to_csv(os.path.join(DATA, "io.csv"), index=False, float_format="%.4f")


# ─── Рисунки ─────────────────────────────────────────────────────────────────
def figures():
    rp.set_latex_mode()
    os.makedirs(FIG, exist_ok=True)

    # Рисунок 1 — верификация
    h = pd.read_csv(os.path.join(DATA, "validation_history.csv"))
    h = h[h["time"] > 0]
    ex = rp.analytic_center(h["time"], ALPHA, 20, 100)
    t = h["time"] / 3600
    rp.figure_pair(
        dict(x=None, y=None, xlabel="$t$, ч", ylabel="$T$, °C",
             series=[(t, h["T_center"], "численное"),
                     (t, ex, "аналитическое")], legend_loc="lower right"),
        dict(x=t, y=np.abs(h["T_center"] - ex), legend=None,
             xlabel="$t$, ч", ylabel=r"$|T_c - T_{ан}|$, °C"),
        "", out_path=os.path.join(FIG, "validation"), fmts=("pdf", "png"),
        legend_top=True)

    # Рисунок 2 — ускорение и эффективность
    rp.fig_speedup(os.path.join(DATA, "benchmark.csv"), FIG,
                   fmts=("pdf", "png"))

    # Рисунок 3 — влияние записи результатов (закон Амдала)
    io = pd.read_csv(os.path.join(DATA, "io.csv"))
    base = io[io["writes"] == 0].iloc[0]
    t_io = io["t1"] - base["t1"]                       # время записи (1 поток)
    model = io["t1"] / (t_io + base["t4"])             # запись не ускоряется
    rp.figure_pair(
        dict(x=None, y=None, xlabel="число записей $M$", ylabel="время, с",
             series=[(io["writes"], io["t1"], "$p = 1$"),
                     (io["writes"], io["t4"], "$p = 4$")]),
        dict(x=None, y=None, xlabel="число записей $M$",
             ylabel=r"ускорение $S_4$",
             series=[(io["writes"], io["speedup"], "замер"),
                     (io["writes"], model, "модель")]),
        "", out_path=os.path.join(FIG, "io"), fmts=("pdf", "png"))
    print("  рисунки:", sorted(os.listdir(FIG)))


def main():
    os.makedirs(DATA, exist_ok=True)
    if "--figs" not in sys.argv:
        with tempfile.TemporaryDirectory() as tmp:
            print("1. Верификация");        exp_validation(tmp)
            print("2. Сходимость");         exp_convergence(tmp)
            print("3. Масштабируемость");   exp_scaling(tmp)
            print("4. Влияние записи");     exp_io(tmp)
    figures()


if __name__ == "__main__":
    main()
