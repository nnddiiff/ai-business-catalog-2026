#!/usr/bin/env python3
"""Перенос результатов адверсариальной проверки из data/proverka.json в карточки семей.

Прогон каталога оборвался на 93% недельного лимита раньше, чем правки скептиков были
сведены с карточками: 138 оспоренных вердиктов по России и 163 уточнённые или
опровергнутые цифры лежали отдельным файлом, а карточки и плоский индекс продолжали
показывать доопровергнутую версию. Скрипт вносит их в сами карточки — новым полем
`proverka` — и дописывает в конец файла семьи те правки цифр, которые к конкретной
карточке не привязываются.

Идемпотентен: поле `proverka` и раздел проверки в файле семьи перезаписываются целиком.

Запуск: python3 site/apply_proverka.py [--check]
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import parse_family  # noqa: E402
from normalize import normalize_file  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAMILIES = ROOT / "catalog" / "families"
DATA = ROOT / "catalog" / "data"


def proverka_files() -> list[Path]:
    """Все журналы проверки: исходный прогон плюс более поздние заходы скептиков."""
    return sorted(DATA.glob("proverka*.json"))

SECTION_MARK = "## Проверка скептиком: правки к цифрам этой семьи"
VERDICTS = ("частично", "занято", "свободно", "нет данных")
# Шкала «насколько ниша занята»: при расхождении заходов выигрывает больший ранг.
VERDICT_RANK = {"нет данных": 0, "свободно": 1, "частично": 2, "занято": 3}


def short_verdict(text: str) -> str:
    """Достаёт нормализованный вердикт из свободной формулировки скептика."""
    low = str(text).strip().lower().lstrip("«\"' ")
    for v in VERDICTS:
        if low.startswith(v):
            return v
    for v in VERDICTS:
        if re.search(rf"\b{v}\b", low[:120]):
            return v
    return ""


def drop_verdict_prefix(text: str) -> str:
    """Срезает начальное слово-вердикт: заголовок правки его уже назвал."""
    t = str(text).strip()
    for v in VERDICTS:
        if t.lower().startswith(v):
            rest = t[len(v):].lstrip(" —–-:;,.")
            return rest or t
    return t


def one_line(text: str, limit: int = 0) -> str:
    """Схлопывает многострочную цитату в одну строку markdown-списка."""
    t = re.sub(r"\s+", " ", str(text)).strip()
    if limit and len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return t


def family_code(raw: str) -> str:
    m = re.match(r"\s*([0-9]{1,2}[AB]?)", str(raw))
    return m.group(1) if m else ""


def load() -> tuple[dict, dict, dict]:
    """Готовит правки: по id карточки — вердикты и цифры, по семье — непривязанные цифры."""
    data: list[dict] = []
    for path in proverka_files():
        chunk = json.loads(path.read_text(encoding="utf-8"))
        data += chunk if isinstance(chunk, list) else [chunk]
    ids_by_fam: dict[str, list[str]] = {}
    file_by_fam: dict[str, Path] = {}
    for p in sorted(FAMILIES.glob("*.md")):
        code = p.name.split("-", 1)[0]
        file_by_fam[code] = p
        # Идентификатор берём из поля карточки, а не из заголовка: в части семей
        # заголовок сокращён, и привязка правок по нему молча теряет всю семью.
        ids_by_fam[code] = [c.id for c in parse_family(p).cards]

    verdicts: dict[str, dict] = {}
    numbers: dict[str, list[dict]] = defaultdict(list)
    loose: dict[str, list[dict]] = defaultdict(list)

    for fam in data:
        code = family_code(fam.get("family", ""))
        if code not in file_by_fam:
            continue
        known = ids_by_fam.get(code, [])

        for ch in fam.get("ru_challenges", []):
            for cid in re.split(r"\s*/\s*", str(ch.get("id", "")).strip()):
                cid = cid.strip()
                if cid in known:
                    # По 10 семьям проверка шла в два независимых захода: храним оба,
                    # затирать ранний нельзя — заходы иногда расходятся в выводе.
                    verdicts.setdefault(cid, []).append(ch)

        for corr in fam.get("corrections", []):
            if corr.get("verdict") not in ("опровергнуто", "уточнено"):
                continue
            blob = " ".join(str(corr.get(k, "")) for k in ("claim", "evidence", "correct_value"))
            hits = [cid for cid in known if cid in blob]
            if hits:
                for cid in hits:
                    numbers[cid].append(corr)
            else:
                loose[code].append(corr)
    return verdicts, numbers, loose


def build_proverka_field(cid: str, verdicts: dict, numbers: dict) -> str:
    """Собирает содержимое поля `proverka` для одной карточки."""
    parts: list[str] = []
    passes = verdicts.get(cid) or []
    if passes:
        was = short_verdict(passes[0].get("was"))
        proposed = [short_verdict(ch.get("should_be")) for ch in passes]
        proposed = [p for p in proposed if p]
        # Заходы расходятся — берём более занятый: найденный игрок опровергает пустоту,
        # а его отсутствие у второго проверяющего её не доказывает.
        final = max(proposed, key=lambda v: VERDICT_RANK.get(v, 0)) if proposed else ""
        if final and final != was:
            head = f"**вердикт по России изменён: было «{was or '—'}» → стало «{final}».**"
        else:
            head = "**вердикт по России проверку выдержал.**"
        if len(set(proposed)) > 1:
            head += (
                f" Два независимых захода проверки разошлись "
                f"({', '.join('«' + p + '»' for p in proposed)}); взят более занятый."
            )
        parts.append(f"- {head}")
        for ch in passes:
            why = one_line(drop_verdict_prefix(ch.get("should_be")))
            if why:
                parts.append(f"  - {why}")
            if ch.get("found"):
                parts.append(f"    Найдено при проверке: {one_line(ch.get('found'))}")
    for corr in numbers.get(cid, []):
        mark = "опровергнуто" if corr.get("verdict") == "опровергнуто" else "уточнено"
        parts.append(f"- **{mark}:** «{one_line(corr.get('claim'), 300)}»")
        if corr.get("correct_value"):
            parts.append(f"  Верное значение: {one_line(corr.get('correct_value'))}")
        if corr.get("evidence"):
            parts.append(f"  Чем проверено: {one_line(corr.get('evidence'), 700)}")
    return "\n".join(parts)


def loose_section(code: str, items: list[dict]) -> str:
    """Раздел в конце файла семьи для правок, не привязанных к конкретной карточке."""
    lines = [SECTION_MARK, ""]
    lines.append(
        f"Правки адверсариальной проверки, относящиеся к семье целиком, а не к одной "
        f"карточке ({len(items)} шт.). Правки, привязанные к карточке, стоят в самой "
        f"карточке полем `proverka`. Источник — `../data/proverka.json`."
    )
    lines.append("")
    for corr in items:
        mark = "Опровергнуто" if corr.get("verdict") == "опровергнуто" else "Уточнено"
        lines.append(f"**{mark}.** «{one_line(corr.get('claim'), 400)}»")
        lines.append("")
        if corr.get("correct_value"):
            lines.append(f"Верное значение: {one_line(corr.get('correct_value'))}")
            lines.append("")
        if corr.get("evidence"):
            lines.append(f"Чем проверено: {one_line(corr.get('evidence'), 900)}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_loose(path: Path, code: str, items: list[dict]) -> None:
    """Дописывает (или обновляет) раздел непривязанных правок в конце файла семьи."""
    text = path.read_text(encoding="utf-8")
    idx = text.find(SECTION_MARK)
    if idx != -1:
        text = text[:idx].rstrip() + "\n"
    if items:
        text = text.rstrip() + "\n\n---\n\n" + loose_section(code, items)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    check = "--check" in sys.argv
    verdicts, numbers, loose = load()

    changed_cards = 0
    problems: list[str] = []

    def transform(cid: str, fields: dict) -> dict:
        nonlocal changed_cards
        value = build_proverka_field(cid, verdicts, numbers)
        if value:
            fields["proverka"] = value
            changed_cards += 1
        else:
            fields.pop("proverka", None)
        return fields

    for path in sorted(FAMILIES.glob("*.md")):
        _, probs = normalize_file(path, check_only=check, transform=transform)
        problems += probs
        if not check and not probs:
            write_loose(path, path.name.split("-", 1)[0], loose.get(path.name.split("-", 1)[0], []))

    print(f"вердиктов по России из проверки: {len(verdicts)}")
    print(f"правок цифр, привязанных к карточкам: {sum(len(v) for v in numbers.values())}")
    print(f"правок цифр в разделы семей: {sum(len(v) for v in loose.values())}")
    print(f"карточек с полем proverka: {changed_cards}")
    if problems:
        print(f"РАСХОЖДЕНИЯ ({len(problems)}):")
        for p in problems[:30]:
            print("   ", p)
        sys.exit(1)


if __name__ == "__main__":
    main()
