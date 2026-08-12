#!/usr/bin/env python3
"""Приведение карточек каталога к единому формату полей.

Агенты прогона записали карточки тремя способами: списком («- **id**: v»),
двухколоночной таблицей («| `id` | v |») и прозой («**money.** v»). Разнобой ломал
сборку сайта и мешает машинной обработке. Скрипт переписывает ТОЛЬКО блоки карточек,
не трогая вступление семьи, мини-индекс и приложения, и проверяет, что после
перезаписи разбор даёт ровно те же значения полей.

Запуск: python3 site/normalize.py [--check]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import CARD_RE, FIELD_ORDER, HEADING_RE, parse_card  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAMILIES = ROOT / "catalog" / "families"

# Порядок полей в карточке — как в задании prompt/PROMPT.md.
WRITE_ORDER = ["id", "name", "one_liner", "family"] + [
    f for f in FIELD_ORDER if f != "one_liner"
]


def squash(text: str) -> str:
    """Схлопывает пробелы и переносы: сравнение значений не должно зависеть от отступов."""
    return re.sub(r"\s+", " ", text).strip()


def render_field(key: str, value: str) -> list[str]:
    """Поле в едином виде. Многострочное значение уходит под метку с отступом."""
    value = value.strip()
    if not value:
        return [f"- **{key}**:"]
    multiline = "\n" in value or re.match(r"^(?:[-*+]\s+|\d+[.)]\s+|\|)", value)
    if not multiline:
        return [f"- **{key}**: {value}"]
    out = [f"- **{key}**:"]
    for line in value.split("\n"):
        out.append(f"  {line.strip()}" if line.strip() else "")
    return out


def normalize_file(path: Path, check_only: bool = False, transform=None) -> tuple[int, list[str]]:
    """Перезаписывает блоки карточек файла. Возвращает число карточек и список расхождений.

    `transform(card_id, fields) -> fields` позволяет менять содержимое карточек тем же
    проверяемым способом: контроль сверяет только неизменённые поля.
    """
    lines = path.read_text(encoding="utf-8").split("\n")
    fam_code = path.name.split("-", 1)[0]
    marks = [(i, HEADING_RE.match(l)) for i, l in enumerate(lines)]
    marks = [(i, m) for i, m in marks if m]
    bounds = [i for i, _ in marks] + [len(lines)]

    replacements: list[tuple[int, int, list[str]]] = []
    problems: list[str] = []
    count = 0
    for idx, (start, _m) in enumerate(marks):
        end = bounds[idx + 1]
        block = lines[start:end]
        cm = CARD_RE.match(block[0])
        if not cm:
            continue
        count += 1
        card = parse_card(cm.group(1), cm.group(2).strip(), fam_code, block[1:])

        # id, name и family парсер уносит в отдельные атрибуты — возвращаем их в поля,
        # иначе перезапись молча съест эти три строки карточки.
        fields = dict(card.fields)
        fields.setdefault("id", card.id)
        fields.setdefault("name", card.name)
        fields.setdefault("family", card.family)
        touched: set[str] = set()
        if transform is not None:
            before = dict(fields)
            fields = transform(card.id, fields)
            touched = {k for k in set(before) | set(fields) if before.get(k) != fields.get(k)}
        body: list[str] = [block[0], ""]
        for key in WRITE_ORDER:
            if key in ("id", "name"):
                body += render_field(key, fields[key])
            elif key in fields:
                body += render_field(key, fields[key])
        for key, value in fields.items():          # поля вне канонического порядка не теряем
            if key not in WRITE_ORDER:
                body += render_field(key, value)
        if card.notes.strip():                      # текст, не привязанный к полю, остаётся как есть
            body += ["", card.notes.rstrip()]
        # хвостовые пустые строки и разделитель исходного блока сохраняем
        tail: list[str] = []
        for line in reversed(block):
            if line.strip() and not re.match(r"^\s*(?:---+|\*\*\*+)\s*$", line):
                break
            tail.insert(0, line)
        body += tail if tail else [""]

        # контроль: разбор нового блока обязан дать те же значения полей
        again = parse_card(cm.group(1), cm.group(2).strip(), fam_code, body[1:])
        for key, value in fields.items():
            if key in ("id", "name", "family"):
                continue
            if squash(again.fields.get(key, "")) != squash(value):
                problems.append(f"{path.name}:{card.id}:{key}")
        for key, value in card.fields.items():          # ничего не пропало при перезаписи
            if key not in fields and key not in touched:
                problems.append(f"{path.name}:{card.id}:{key}:потеряно")
        for attr in ("id", "name", "family"):
            if squash(getattr(again, attr)) != squash(fields.get(attr, "")):
                problems.append(f"{path.name}:{card.id}:{attr}")
        replacements.append((start, end, body))

    if not check_only and not problems:
        for start, end, body in reversed(replacements):
            lines[start:end] = body
        text = "\n".join(lines)
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return count, problems


def main() -> None:
    check = "--check" in sys.argv
    total, bad = 0, []
    for path in sorted(FAMILIES.glob("*.md")):
        count, problems = normalize_file(path, check_only=check)
        total += count
        bad += problems
    print(f"карточек обработано: {total}")
    if bad:
        print(f"РАСХОЖДЕНИЯ ({len(bad)}), файлы не переписаны:")
        for b in bad[:40]:
            print("   ", b)
        sys.exit(1)
    print("значения полей после перезаписи совпадают с исходными")


if __name__ == "__main__":
    main()
