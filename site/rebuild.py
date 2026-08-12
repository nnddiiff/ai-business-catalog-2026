#!/usr/bin/env python3
"""Полная пересборка каталога и сайта одной командой.

Порядок шагов существен: правки проверки должны попасть в карточки раньше, чем из них
берётся вердикт, а индексы и сайт собираются последними — из уже согласованных карточек.

Запуск: python3 site/rebuild.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

STEPS = [
    ("apply_proverka.py", "вносит правки скептиков в карточки"),
    ("set_verdicts.py", "фиксирует вердикт по России полем карточки"),
    ("mark_duplicates.py", "размечает повторы идей между семьями"),
    ("render_proverka.py", "пересобирает свод проверки"),
    ("reindex.py", "пересчитывает плоский и машинный индексы"),
    ("build.py", "собирает статический сайт в docs/"),
]


def main() -> None:
    for script, what in STEPS:
        print(f"\n=== {script} — {what}")
        result = subprocess.run([sys.executable, str(HERE / script)], check=False)
        if result.returncode != 0:
            print(f"\nОстановлено: {script} завершился с кодом {result.returncode}")
            sys.exit(result.returncode)
    print("\nГотово: карточки, индексы и сайт согласованы.")


if __name__ == "__main__":
    main()
