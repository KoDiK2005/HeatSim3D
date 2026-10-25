# -*- coding: utf-8 -*-
"""Проверка параллельной OpenMP-версии heat3d.

1. Результат не зависит от числа потоков (поле температуры совпадает побитно).
2. Флаг --threads реально задаёт число потоков OpenMP.
3. Численное решение сходится к аналитическому (ряд Фурье для куба).
4. Windows-сборка heat3d.exe даёт те же числа (если установлен wine).

Запуск: python -m pytest tests/integration/test_openmp.py -v
"""
import glob
import math
import os
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO_ROOT, "heat3d.cpp")

ARGS = ["--nx", "21", "--ny", "21", "--nz", "21", "--t_end", "8000",
        "--t_init", "20", "--t_xm", "300", "--save_every", "100"]


@pytest.fixture(scope="session")
def engine(tmp_path_factory):
    """Свежая сборка heat3d.cpp с OpenMP."""
    exe = tmp_path_factory.mktemp("build") / "heat3d"
    subprocess.run(["g++", "-O2", "-fopenmp", "-std=c++17", SRC, "-o", str(exe)],
                   check=True)
    return str(exe)


def run(cmd, workdir):
    os.makedirs(workdir, exist_ok=True)
    out = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                         check=True).stdout
    return out, os.path.join(workdir, "output")


def read_slices(out_dir):
    files = sorted(glob.glob(os.path.join(out_dir, "slice_*.csv")))
    assert files, "срезы не записаны"
    return {os.path.basename(f): pd.read_csv(f)["T"].values for f in files}


def test_result_independent_of_threads(engine, tmp_path):
    _, d1 = run([engine, *ARGS, "--threads", "1"], tmp_path / "p1")
    _, d4 = run([engine, *ARGS, "--threads", "4"], tmp_path / "p4")
    s1, s4 = read_slices(d1), read_slices(d4)
    assert s1.keys() == s4.keys()
    for name in s1:
        assert np.array_equal(s1[name], s4[name]), name
    h1 = pd.read_csv(os.path.join(d1, "history.csv"))
    h4 = pd.read_csv(os.path.join(d4, "history.csv"))
    # T_mean считается редукцией — допускаем расхождение в последнем знаке
    assert np.allclose(h1.values, h4.values, atol=1e-3)


@pytest.mark.parametrize("p", [1, 2, 3])
def test_threads_flag(engine, tmp_path, p):
    out, d = run([engine, *ARGS, "--threads", str(p)], tmp_path)
    assert f"Threads   : {p}" in out
    prm = pd.read_csv(os.path.join(d, "params.csv"))
    assert int(dict(zip(prm.key, prm.value))["threads"]) == p


def analytic_center(t, alpha, t0, tb, terms=60):
    """T в центре единичного куба, все грани tb, начальное t0."""
    s = 0.0
    for l in range(1, terms, 2):
        for m in range(1, terms, 2):
            for n in range(1, terms, 2):
                sign = (-1) ** ((l - 1) // 2 + (m - 1) // 2 + (n - 1) // 2)
                s += sign * 64 / (math.pi ** 3 * l * m * n) * \
                     math.exp(-alpha * math.pi ** 2 * (l * l + m * m + n * n) * t)
    return tb + (t0 - tb) * s


def test_matches_analytic_solution(engine, tmp_path):
    alpha = 1.28e-5
    _, d = run([engine, "--nx", "31", "--ny", "31", "--nz", "31",
                "--alpha", str(alpha), "--t_end", "6000", "--t_init", "20",
                "--t_xm", "100", "--t_xp", "100", "--t_ym", "100",
                "--t_yp", "100", "--t_zm", "100", "--t_zp", "100",
                "--save_every", "50"], tmp_path)
    h = pd.read_csv(os.path.join(d, "history.csv"))
    h = h[h.time > 500]           # в самом начале ряд сходится медленно
    exact = np.array([analytic_center(t, alpha, 20, 100) for t in h.time])
    err = np.abs(h.T_center.values - exact).max()
    assert err < 0.5, f"макс. отклонение от аналитики {err:.3f} °C"


@pytest.mark.skipif(not shutil.which("x86_64-w64-mingw32-g++-posix")
                    or not shutil.which("wine"),
                    reason="нужны mingw-w64 и wine")
def test_windows_build_matches_linux(engine, tmp_path):
    exe = tmp_path / "heat3d.exe"
    subprocess.run(["x86_64-w64-mingw32-g++-posix", "-O2", "-fopenmp",
                    "-std=c++17", "-static", SRC, "-o", str(exe)], check=True)
    env = dict(os.environ, WINEDEBUG="-all",
               WINEPREFIX=str(tmp_path.parent / "wineprefix"))
    wdir = tmp_path / "win"
    wdir.mkdir()
    subprocess.run(["wine", str(exe), *ARGS, "--threads", "2"], cwd=wdir,
                   env=env, capture_output=True, check=True, timeout=300)
    _, dl = run([engine, *ARGS, "--threads", "2"], tmp_path / "lin")
    sw, sl = read_slices(wdir / "output"), read_slices(dl)
    for name in sl:
        assert np.array_equal(sw[name], sl[name]), name
