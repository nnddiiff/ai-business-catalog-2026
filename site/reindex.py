#!/usr/bin/env python3
"""Пересчёт вердиктов по России в плоском индексе и машинном оглавлении каталога.

Источник истины — карточки `families/*.md`: вердикт берётся из поля `proverka`
(результат адверсариальной проверки), при его отсутствии — из `ru_analog`.
Скрипт синхронизирует с ними `catalog/00-index.md` и `catalog/data/index.json`,
сохраняя в последнем «самую говорящую цифру» из прежней версии.

Запуск: python3 site/reindex.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import (  # noqa: E402
    CATALOG, VERDICTS, card_verdict, derive_verdict, parse_family, verdict_from_proverka,
)

INDEX_MD = CATALOG / "00-index.md"
INDEX_JSON = CATALOG / "data" / "index.json"
ROW_RE = re.compile(r"^\|\s*([A-Za-z]{0,3}\d{1,2}[A-Za-z]?(?:-[A-Za-z0-9]+)+)\s*\|")


def current_verdicts() -> tuple[dict[str, str], list]:
    """Вердикт по каждой карточке и разобранные семьи."""
    families = [parse_family(p) for p in sorted((CATALOG / "families").glob("*.md"))]
    families.sort(key=lambda f: (int(re.sub(r"\D", "", f.code) or 0), f.code))
    verdicts: dict[str, str] = {}
    for fam in families:
        for card in fam.cards:
            verdicts[card.id] = (
                card_verdict(card.fields.get("ru_verdict", ""))
                or verdict_from_proverka(card.fields.get("proverka", ""))
                or derive_verdict(card.fields.get("ru_analog", ""))
            )
    return verdicts, families


def update_index_md(verdicts: dict[str, str]) -> tuple[int, int]:
    """Переписывает колонку вердикта в плоском индексе. Возвращает (строк, изменено)."""
    lines = INDEX_MD.read_text(encoding="utf-8").split("\n")
    rows = changed = 0
    for i, line in enumerate(lines):
        m = ROW_RE.match(line)
        if not m or m.group(1) not in verdicts:
            continue
        cells = line.split("|")
        if len(cells) < 6:
            continue
        rows += 1
        want = verdicts[m.group(1)]
        if cells[4].strip() != want:
            cells[4] = f" {want} "
            lines[i] = "|".join(cells)
            changed += 1
    INDEX_MD.write_text("\n".join(lines), encoding="utf-8")
    return rows, changed


def update_totals(counts: dict[str, int], total: int) -> None:
    """Обновляет итоговую строку в индексе и в README каталога."""
    summary = (
        f"{total} идей, 23 семьи по таксономии (26 файлов — семьи 1, 4 и 5 разбиты на "
        f"подсемьи A/B). По России: {counts['частично']} частично, {counts['занято']} занято, "
        f"{counts['свободно']} свободно, {counts['нет данных']} нет данных."
    )
    text = INDEX_MD.read_text(encoding="utf-8")
    text = re.sub(r"\*\*Итог:[^*]+\*\*", f"**Итог: {summary}**", text, count=1)
    INDEX_MD.write_text(text, encoding="utf-8")

    readme = CATALOG / "README.md"
    rt = readme.read_text(encoding="utf-8")
    rt = re.sub(
        r"\*\*\d+ идей, 23 семьи[^*]+\*\*",
        f"**{summary}**",
        rt,
        count=1,
    )
    readme.write_text(rt, encoding="utf-8")


def update_index_json(verdicts: dict[str, str], families) -> tuple[int, int]:
    """Перегенерирует машинное оглавление из карточек, сохраняя key_number прежней версии."""
    old_key: dict[str, str] = {}
    if INDEX_JSON.exists():
        for fam in json.loads(INDEX_JSON.read_text(encoding="utf-8")):
            for it in fam.get("ideas") or []:
                if it.get("key_number"):
                    old_key[it["id"]] = it["key_number"]

    out = []
    total = 0
    for fam in families:
        ideas = []
        for card in fam.cards:
            total += 1
            ideas.append({
                "id": card.id,
                "name": card.name,
                "one_liner": re.sub(r"\s+", " ", card.fields.get("one_liner", "")).strip(),
                "ru": verdicts.get(card.id, ""),
                "key_number": old_key.get(card.id, ""),
            })
        out.append({
            "family": fam.code,
            "title": fam.title,
            "file": f"families/{fam.file}",
            "ideas": ideas,
        })
    INDEX_JSON.write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return len(out), total


def main() -> None:
    verdicts, families = current_verdicts()
    counts = {v: sum(1 for x in verdicts.values() if x == v) for v in VERDICTS}
    rows, changed = update_index_md(verdicts)
    update_totals(counts, len(verdicts))
    fams, total = update_index_json(verdicts, families)
    print(f"00-index.md: строк идей {rows}, вердиктов исправлено {changed}")
    print(f"data/index.json: семей {fams}, идей {total}")
    print("вердикты:", counts)


if __name__ == "__main__":
    main()
