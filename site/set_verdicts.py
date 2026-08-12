#!/usr/bin/env python3
"""Фиксация вердикта по России отдельным полем карточки.

До этого вердикт жил в трёх местах сразу: в машинном оглавлении `data/index.json`
(как его определил агент семьи), в плоском индексе `00-index.md` и в свободном тексте
поля `ru_analog`, а результат адверсариальной проверки не попадал ни в одно из них.
Скрипт сводит их в одно поле `ru_verdict` внутри карточки, после чего markdown
становится единственным источником истины, а индексы — производными.

Приоритет: проверка скептика (`proverka`) → прежний вердикт агента (`data/index.json`)
→ разбор свободного текста `ru_analog`.

Запуск: python3 site/set_verdicts.py [--check]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import CATALOG, VERDICTS, derive_verdict, verdict_from_proverka  # noqa: E402
from normalize import normalize_file  # noqa: E402

FAMILIES = CATALOG / "families"


def agent_verdicts() -> dict[str, str]:
    """Вердикты, проставленные агентами семей при сборе каталога."""
    path = CATALOG / "data" / "index.json"
    out: dict[str, str] = {}
    if path.exists():
        for fam in json.loads(path.read_text(encoding="utf-8")):
            for it in fam.get("ideas") or []:
                if it.get("ru") in VERDICTS:
                    out[it["id"]] = it["ru"]
    return out


def main() -> None:
    check = "--check" in sys.argv
    prior = agent_verdicts()
    stats: Counter[str] = Counter()
    verdicts: Counter[str] = Counter()
    problems: list[str] = []

    def transform(cid: str, fields: dict) -> dict:
        from_check = verdict_from_proverka(fields.get("proverka", ""))
        existing = (fields.get("ru_verdict") or "").strip().lower()
        if from_check:
            verdict, source = from_check, "проверка"
        elif existing in VERDICTS:
            verdict, source = existing, "уже в карточке"
        elif cid in prior:
            verdict, source = prior[cid], "агент"
        else:
            verdict, source = derive_verdict(fields.get("ru_analog", "")), "текст"
        stats[source] += 1
        verdicts[verdict] += 1
        fields["ru_verdict"] = verdict
        return fields

    for path in sorted(FAMILIES.glob("*.md")):
        _, probs = normalize_file(path, check_only=check, transform=transform)
        problems += probs

    print("источник вердикта:", dict(stats))
    print("вердикты:", dict(verdicts))
    if problems:
        print(f"РАСХОЖДЕНИЯ ({len(problems)}):")
        for p in problems[:30]:
            print("   ", p)
        sys.exit(1)


if __name__ == "__main__":
    main()
