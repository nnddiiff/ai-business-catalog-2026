#!/usr/bin/env python3
"""Пересчёт вводного раздела `catalog/99-neproverennoe.md` по фактическому покрытию.

Раздел описывает, что именно в каталоге не проверено и чем это ослабляет вердикты.
Раньше он был написан руками и устаревал при каждом новом заходе скептика. Теперь
цифры считаются из самих данных: какие семьи прошли адверсариальную проверку, сколько
вердиктов «свободно» её прошли, а сколько держатся только на первичном поиске.

Правится только блок между маркерами; всё, что ниже, — сведение из семейных файлов.

Запуск: python3 site/render_status.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import CATALOG, VERDICTS, card_verdict, derive_verdict, parse_family, verdict_from_proverka  # noqa: E402

TARGET = CATALOG / "99-neproverennoe.md"
BEGIN = "<!-- статус: начало автоблока -->"
END = "<!-- статус: конец автоблока -->"


def coverage() -> tuple[set[str], set[str], int, int, list[str]]:
    """Кто проверен скептиком: семьи и вердикты «свободно»."""
    checked_fams: set[str] = set()
    for path in sorted((CATALOG / "data").glob("proverka*.json")):
        chunk = json.loads(path.read_text(encoding="utf-8"))
        for fam in (chunk if isinstance(chunk, list) else [chunk]):
            m = re.match(r"\s*([0-9]{1,2}[AB]?)", str(fam.get("family", "")))
            if m:
                checked_fams.add(m.group(1))

    all_fams: set[str] = set()
    free_checked = free_raw = 0
    raw_ids: list[str] = []
    for path in sorted((CATALOG / "families").glob("*.md")):
        fam = parse_family(path)
        all_fams.add(path.name.split("-", 1)[0])
        for card in fam.cards:
            verdict = (
                card_verdict(card.fields.get("ru_verdict", ""))
                or verdict_from_proverka(card.fields.get("proverka", ""))
                or derive_verdict(card.fields.get("ru_analog", ""))
            )
            if verdict != "свободно":
                continue
            if card.fields.get("proverka"):
                free_checked += 1
            else:
                free_raw += 1
                raw_ids.append(card.id)
    return checked_fams, all_fams, free_checked, free_raw, raw_ids


def block() -> str:
    checked, all_fams, free_checked, free_raw, raw_ids = coverage()
    missing = sorted(all_fams - checked, key=lambda c: (int(re.sub(r"\D", "", c) or 0), c))
    lines = [
        BEGIN,
        "",
        "## Что проверено скептиком, а что нет",
        "",
        f"Адверсариальную проверку прошли **{len(checked)} семьи из {len(all_fams)}**.",
    ]
    if missing:
        lines.append(
            f"Без проверки остаются: {', '.join(missing)} — вердикты по ним держатся "
            f"только на том, что нашёл или не нашёл агент семьи."
        )
    else:
        lines.append("Семей без адверсариальной проверки не осталось.")
    lines += [
        "",
        f"Из вердиктов «свободно» проверку прошли **{free_checked} из "
        f"{free_checked + free_raw}**; остальные {free_raw} держатся на первичном поиске "
        f"одного агента.",
        "",
        "Почему это важно именно для «свободно»: в предыдущем прогоне этого же проекта "
        "(`../research/`) целевой проход по российским сторам и каталогам убил "
        "**6 кандидатов из 8**, уже прошедших ту же первичную проверку. Там, где скептик "
        "проходил по вердиктам заново, направление правок всегда одно — ниша оказывается "
        "занята плотнее, чем считал первый агент. Единственное исключение за все заходы — "
        "`C17-agent-identity-authz`, где вердикт понижен до «свободно», и то не по новой "
        "находке, а потому что прежнее «частично» не подтверждалось собственным текстом "
        "карточки.",
        "",
        "Поэтому вердикт «свободно» здесь правильно читать как «не найдено при нынешней "
        "глубине поиска», а не как доказанную пустоту рынка. Непроверенные «свободно» "
        "перед любым решением нужно атаковать отдельно — русскими словами задачи, а не "
        "калькой с английского термина: именно так находилось большинство пропущенных "
        "российских игроков.",
        "",
    ]
    if raw_ids:
        lines += [
            "Непроверенные вердикты «свободно»: "
            + ", ".join(f"`{i}`" for i in sorted(raw_ids)) + ".",
            "",
        ]
    lines += [
        "Не выполнены сквозные проходы по российским каналам сбыта — сторы и мобильные "
        "приложения; vc.ru, Habr, Product Radar; CNews, TAdviser, госзакупки и "
        "интеграторы; каталоги телеграм-ботов и VK Mini Apps, — а также три отдельные "
        "охоты за провалами. Раздел `90-provaly.md` собран из того, что попалось агентам "
        "семей попутно, поэтому число провалов в нём — нижняя граница.",
        "",
        "Этот блок пересчитывается скриптом `site/render_status.py`; ниже — сведение "
        "разделов «Что не проверено и почему» из файлов семей.",
        "",
        END,
    ]
    return "\n".join(lines)


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    new = block()
    if BEGIN in text and END in text:
        text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), new, text, flags=re.S)
    else:
        # первый запуск: автоблок встаёт вместо написанной руками вводной части,
        # всё, что ниже разделителя со сведением по семьям, сохраняется
        head, sep, tail = text.partition("\n---\n")
        title = head.split("\n", 1)[0]
        text = f"{title}\n\n{new}\n{sep}{tail}" if sep else f"{title}\n\n{new}\n"
    TARGET.write_text(text, encoding="utf-8")
    checked, all_fams, free_checked, free_raw, _ = coverage()
    print(f"99-neproverennoe.md: семей с проверкой {len(checked)}/{len(all_fams)}, "
          f"«свободно» проверено {free_checked}, без проверки {free_raw}")


if __name__ == "__main__":
    main()
