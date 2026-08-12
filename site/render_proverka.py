#!/usr/bin/env python3
"""Сборка свода адверсариальной проверки `catalog/40-proverka.md`.

Прежний свод был одной таблицей, в ячейки которой попали абзацы прозы: строки до
3061 знака, читать невозможно ни в редакторе, ни на телефоне. Здесь то же содержание
разложено по семьям блоками, а сами правки живут в карточках (поле `proverka`).

Файл производный: собирается из `catalog/data/proverka*.json`, вручную не правится.

Запуск: python3 site/render_proverka.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from apply_proverka import (  # noqa: E402
    VERDICT_RANK, family_code, one_line, proverka_files, short_verdict,
)
from build import CATALOG  # noqa: E402

OUT = CATALOG / "40-proverka.md"
ORDER = {"опровергнуто": 0, "уточнено": 1, "не проверяемо": 2, "подтверждено": 3}


def family_titles() -> dict[str, str]:
    """Название семьи по её коду — из первой строки файла семьи."""
    out: dict[str, str] = {}
    for path in sorted((CATALOG / "families").glob("*.md")):
        code = path.name.split("-", 1)[0]
        first = path.read_text(encoding="utf-8").split("\n", 1)[0]
        out[code] = re.sub(r"^#+\s*(?:Семья\s+)?[0-9AB]+[.:]?\s*", "", first).strip()
    return out


def main() -> None:
    data: list[dict] = []
    for path in proverka_files():
        chunk = json.loads(path.read_text(encoding="utf-8"))
        data += chunk if isinstance(chunk, list) else [chunk]

    titles = family_titles()
    corrections: dict[str, list[dict]] = defaultdict(list)
    challenges: dict[str, list[dict]] = defaultdict(list)
    for fam in data:
        code = family_code(fam.get("family", ""))
        if not code:
            continue
        corrections[code] += fam.get("corrections", [])
        challenges[code] += fam.get("ru_challenges", [])

    stats: Counter[str] = Counter()
    for items in corrections.values():
        for c in items:
            stats[str(c.get("verdict", "не указано"))] += 1
    moved = to_taken = 0
    for items in challenges.values():
        for ch in items:
            was, should = short_verdict(ch.get("was")), short_verdict(ch.get("should_be"))
            if should and was and should != was:
                moved += 1
                if VERDICT_RANK.get(should, 0) > VERDICT_RANK.get(was, 0):
                    to_taken += 1

    covered = sorted(set(corrections) | set(challenges),
                     key=lambda c: (int(re.sub(r"\D", "", c) or 0), c))
    total_c = sum(len(v) for v in corrections.values())
    total_v = sum(len(v) for v in challenges.values())

    out: list[str] = [
        "# Адверсариальная проверка каталога: свод",
        "",
        "Независимый скептик атаковал по каждой семье самые несущие цифры файла и вердикты "
        "по России, заходя другими словами и другими каналами, чем исходный агент. Здесь "
        "сводка; сами правки внесены в карточки — поле `proverka` в `families/*.md`.",
        "",
        f"**Проверено {total_c} утверждений и {total_v} вердиктов по России по {len(covered)} "
        f"семьям из 26.** Из утверждений: подтверждено {stats.get('подтверждено', 0)}, "
        f"уточнено {stats.get('уточнено', 0)}, опровергнуто {stats.get('опровергнуто', 0)}, "
        f"признано непроверяемым {stats.get('не проверяемо', 0)}. "
        f"Вердикт по России изменён в {moved} случаях из {total_v}, "
        f"и в {to_taken} из них — в сторону «ниша занята плотнее», а не свободнее.",
        "",
        "Файл производный: собирается скриптом `site/render_proverka.py` из "
        "`data/proverka*.json`, вручную не правится.",
        "",
    ]

    for code in covered:
        title = titles.get(code, "")
        out.append(f"## Семья {code}. {title}".rstrip(". "))
        out.append("")

        ch_items = challenges.get(code, [])
        if ch_items:
            out.append(f"### Вердикты по России ({len(ch_items)})")
            out.append("")
            for ch in ch_items:
                out.append(f"**`{ch.get('id', '—')}`.** Было: {one_line(ch.get('was'))}")
                out.append("")
                out.append(f"Стало: {one_line(ch.get('should_be'))}")
                out.append("")
                if ch.get("found"):
                    out.append(f"Чем обосновано: {one_line(ch.get('found'))}")
                    out.append("")

        c_items = sorted(
            corrections.get(code, []),
            key=lambda c: ORDER.get(str(c.get("verdict")), 9),
        )
        if c_items:
            out.append(f"### Цифры и утверждения ({len(c_items)})")
            out.append("")
            for c in c_items:
                out.append(
                    f"**{str(c.get('verdict', '')).capitalize()}.** "
                    f"«{one_line(c.get('claim'), 400)}»"
                )
                out.append("")
                if c.get("correct_value"):
                    out.append(f"Верное значение: {one_line(c.get('correct_value'))}")
                    out.append("")
                if c.get("evidence"):
                    out.append(f"Чем проверено: {one_line(c.get('evidence'), 900)}")
                    out.append("")

    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).rstrip() + "\n"
    OUT.write_text(text, encoding="utf-8")
    widest = max(len(l) for l in text.split("\n"))
    print(f"40-proverka.md: {len(text.splitlines())} строк, самая длинная {widest} знаков")
    print(f"семей: {len(covered)}, утверждений: {total_c}, вердиктов: {total_v}")


if __name__ == "__main__":
    main()
