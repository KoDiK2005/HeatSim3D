# Отчёт по НИР, 7 семестр — параллельная OpenMP-версия HeatSim3D

Сборка PDF (TeX Live: `disser`, `biblatex-gost`, `cm-super`):

```
pdflatex Thesis && biber Thesis && pdflatex Thesis && pdflatex Thesis
```

Пересчитать все эксперименты и рисунки главы 3 (из корня проекта):

```
python nir_7sem/experiments.py          # замеры + рисунки (несколько минут)
python nir_7sem/experiments.py --figs   # только перерисовать по data/*.csv
```

Красным в PDF (`\fillme{...}`) выделено то, что нужно заполнить самому:
ФИО руководителя полностью, сверка компетенций с учебным планом, отзыв.
