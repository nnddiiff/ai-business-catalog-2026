#!/usr/bin/env python3
"""Разметка повторов между семьями каталога.

Часть идей записана дважды и трижды в разных семьях: совпадают покупатель, состав
игроков и опорная цифра, а иногда и суффикс идентификатора. Из-за этого заявленные
439 идей завышают число различимых. Карточки не удаляются — в них разные источники
и разные проверки, — но повтор помечается явно: вторичная получает `duplicate_of`,
основная и смежные — `see_also`. Счётчик различимых идей считает карточки без
`duplicate_of`.

Пары установлены сверкой полей `one_liner`, `buyer` и `players`, а не эвристикой.

Запуск: python3 site/mark_duplicates.py [--check]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import CATALOG  # noqa: E402
from normalize import normalize_file  # noqa: E402

FAMILIES = CATALOG / "families"

# Повтор одной идеи: совпадают покупатель, состав игроков и суть.
# Формат: вторичная карточка -> (основная карточка, чем обоснован повтор).
DUPLICATES = {
    "C11-synthetic-tabular-privacy": (
        "C14-synthetic-tabular-privacy",
        "тот же предмет и те же игроки (Tonic.ai, Gretel в составе NVIDIA, Betterdata, "
        "YData/MOSTLY AI); синтетика данных профильна для семьи 14",
    ),
    "C11-rl-environments": (
        "C14-rl-environments",
        "та же идея и те же игроки (Prime Intellect, Mercor, Mechanize, Surge); "
        "производство обучающих сред — это данные, то есть семья 14",
    ),
    "C15-mcp-security-scan": (
        "C17-mcp-security",
        "тот же предмет (проверка чужих MCP-серверов и перехват вызовов) и те же игроки "
        "(Snyk после покупки Invariant Labs); профильная семья — безопасность",
    ),
    "C6-app-generator-platform": (
        "H2-text-to-app",
        "полное совпадение состава игроков (Lovable, Replit, Base44, v0, Bolt) и сути",
    ),
    "C7-geo-aeo-visibility": (
        "5A-geo-visibility",
        "та же услуга и те же игроки (Profound, Peec, Otterly, AthenaHQ)",
    ),
    "C19-geo-visibility": (
        "5A-geo-visibility",
        "та же услуга и те же игроки (Profound, Peec, Scrunch, Otterly, AthenaHQ)",
    ),
}

# Пересечение без повтора: общие игроки, но разный предмет покупки или покупатель.
CROSS = [
    ("C11-adapter-marketplace", "C19-model-hub",
     "общие площадки (Civitai, Replicate), но предмет разный: витрина авторских "
     "адаптеров против хаба весов с продажей приватного контура"),
    ("5B-agents-for-accounting-firms", "1A-09-audit-firm-agents",
     "общие игроки (Basis, Fieldguide, Numeric); разделение по форме продажи — "
     "услуга против отраслевого софта"),
    ("C23-aml-alert-agent", "1A-11-aml-kyc-agents",
     "общие игроки (Bretton AI, Lucinity); разделение по контуру — крипто-реформа "
     "против банковского финансового мониторинга"),
    ("5B-injury-demand-packages", "1A-02-plaintiff-case-factory",
     "общие игроки (EvenUp, Supio, Eve); разделение по форме — услуга против продукта"),
]


def build_links() -> tuple[dict, dict]:
    """Готовит содержимое полей duplicate_of и see_also по каждой карточке."""
    dup: dict[str, str] = {}
    see: dict[str, list[str]] = {}
    for secondary, (primary, why) in DUPLICATES.items():
        dup[secondary] = f"`{primary}` — {why}. В счёт различимых идей входит основная карточка."
        see.setdefault(primary, []).append(f"`{secondary}` — та же идея в другой семье")
    for a, b, why in CROSS:
        see.setdefault(a, []).append(f"`{b}` — {why}")
        see.setdefault(b, []).append(f"`{a}` — {why}")
    return dup, see


def main() -> None:
    check = "--check" in sys.argv
    dup, see = build_links()
    marked = {"duplicate_of": 0, "see_also": 0}
    problems: list[str] = []

    def transform(cid: str, fields: dict) -> dict:
        if cid in dup:
            fields["duplicate_of"] = dup[cid]
            marked["duplicate_of"] += 1
        else:
            fields.pop("duplicate_of", None)
        if cid in see:
            fields["see_also"] = "\n".join(f"- {x}" for x in see[cid])
            marked["see_also"] += 1
        else:
            fields.pop("see_also", None)
        return fields

    for path in sorted(FAMILIES.glob("*.md")):
        _, probs = normalize_file(path, check_only=check, transform=transform)
        problems += probs

    print(f"помечено повторов: {marked['duplicate_of']} из {len(DUPLICATES)} ожидаемых")
    print(f"помечено перекрёстных связей: {marked['see_also']}")
    if marked["duplicate_of"] != len(DUPLICATES):
        missing = set(DUPLICATES) - set()
        print("ВНИМАНИЕ: не все повторы найдены в файлах:", sorted(missing))
    if problems:
        print(f"РАСХОЖДЕНИЯ ({len(problems)}):")
        for p in problems[:30]:
            print("   ", p)
        sys.exit(1)


if __name__ == "__main__":
    main()
