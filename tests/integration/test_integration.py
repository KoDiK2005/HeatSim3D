# -*- coding: utf-8 -*-
"""Стык GUI <-> C++-ядра: запуск heat3d, разбор stdout регулярками из gui.py,
чтение history.csv через pandas -- как это делает _draw_history в gui.py.

heat3d.exe в репозитории собран под Windows, поэтому для тестов на Linux
компилируем heat3d.cpp во временный бинарник (фикстура engine).
"""
import os
import re
import subprocess
import sys

import pandas as pd
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)
import gui  # noqa: E402  (реальный gui.py, используем _build_cmd как есть)

BASE_PARAMS = dict(
    nx=30, ny=30, nz=30, alpha=1.28e-5, t_end=50000.0,
    t_init=20.0, t_xm=100.0, t_xp=100.0, t_ym=100.0,
    t_yp=100.0, t_zm=100.0, t_zp=100.0, save_every=500,
)


@pytest.fixture(scope="session")
def engine(tmp_path_factory):
    """Собирает heat3d.cpp под Linux (_mkdir/direct.h заменяем на POSIX)."""
    src = open(os.path.join(REPO_ROOT, "heat3d.cpp"), encoding="utf-8").read()
    src = src.replace("#include <direct.h>", "#include <sys/stat.h>")
    src = src.replace('_mkdir("output")', 'mkdir("output", 0755)')

    build_dir = tmp_path_factory.mktemp("heat3d_build")
    src_path = build_dir / "heat3d.cpp"
    bin_path = build_dir / "heat3d"
    src_path.write_text(src, encoding="utf-8")

    subprocess.run(
        ["g++", "-O2", "-std=c++17", str(src_path), "-o", str(bin_path)],
        check=True,
    )
    return str(bin_path)


def run_engine(engine, params, workdir):
    """Запускает движок ровно так же, как это делает gui.py::_run_thread."""
    cmd = gui.HeatSimApp._build_cmd(None, engine, params)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, cwd=workdir)
    return proc.stdout


def gui_file_estimate(p):
    """Копия формулы из gui.py::_start_sim (предупреждение "Много файлов")."""
    dx = 1.0 / (p["nx"] - 1)
    dt_est = 0.4 / (2.0 * p["alpha"] * 3.0 / (dx * dx))
    return int(p["t_end"] / dt_est / p["save_every"]) + 1


def test_progress_regex_matches_engine_output(engine, tmp_path):
    out = run_engine(engine, BASE_PARAMS, tmp_path)

    total_steps = int(re.search(r"Steps\s*:\s*(\d+)", out).group(1))
    last_step = max(int(m.group(1)) for m in re.finditer(r"step=\s*(\d+)", out))
    last_pct = min(100, last_step / total_steps * 100)

    assert total_steps == 8074
    assert abs(last_pct - 99.09) < 0.1


def test_history_csv_matches_what_gui_expects(engine, tmp_path):
    run_engine(engine, BASE_PARAMS, tmp_path)
    df = pd.read_csv(tmp_path / "output" / "history.csv")

    assert list(df.columns) == ["step", "time", "T_center", "T_mean"]
    assert len(df) == 17  # save_every=500 при 8074 шагах -> 17 точек


def test_file_count_estimate_ignores_ny_nz(engine, tmp_path):
    # Формула из _start_sim дублирует computeStableDt(), но считает dx только
    # по Nx -- для несимметричной сетки предупреждение "Много файлов" молчит,
    # хотя реальных файлов на порядок больше.
    params = dict(BASE_PARAMS, nx=10, ny=80, nz=10)
    predicted = gui_file_estimate(params)

    run_engine(engine, params, tmp_path)
    slices = [f for f in os.listdir(tmp_path / "output") if f.startswith("slice_")]

    assert len(slices) > predicted * 10


def test_save_every_larger_than_run_keeps_only_initial_point(engine, tmp_path):
    # Если t_end даёт меньше шагов, чем save_every, "step % save_every == 0"
    # срабатывает только на step=0 -- финальное состояние расчёта нигде не
    # сохраняется, и движок при этом завершается с кодом 0.
    params = dict(BASE_PARAMS, nx=15, ny=15, nz=15, t_end=5000.0, save_every=500)
    out = run_engine(engine, params, tmp_path)
    nsteps = int(re.search(r"Steps\s*:\s*(\d+)", out).group(1))
    df = pd.read_csv(tmp_path / "output" / "history.csv")

    assert nsteps < params["save_every"]
    assert len(df) == 1
