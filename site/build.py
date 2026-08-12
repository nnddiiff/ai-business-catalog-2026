#!/usr/bin/env python3
"""Сборка статического сайта каталога ИИ-бизнесов из markdown-файлов исследования.

Читает catalog/ и складывает в docs/ готовый сайт для GitHub Pages:
разбирает карточки семей на поля, переносит верхние документы,
переводит markdown в HTML без внешних зависимостей.

Запуск: python3 site/build.py
"""
from __future__ import annotations

import html
import json
import re
import shutil
from dataclasses import dataclass, field as dc_field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog"
ASSETS = Path(__file__).resolve().parent / "assets"
DOCS = ROOT / "docs"

# Заголовок карточки. Идентификаторы у агентов вышли разными: C23-wallet-check,
# 1A-01-legal-copilot, H2-ai-code-editor, F20-lab-deployment-jv — поэтому шаблон широкий:
# необязательные буквы, цифры семьи, необязательная буква подсемьи, дальше слаг через дефисы.
# Разделитель между id и названием — тире или точка, и после него обязателен пробел:
# без этого требования дефис внутри самого id принимается за разделитель и id обрезается
# («C15-mcp-billing-gateway. Шлюз…» превращался в «C15-mcp-billing»).
CARD_RE = re.compile(
    r"^#{2,4}\s+([A-Za-z]{0,3}\d{1,2}[A-Za-z]?(?:-[A-Za-z0-9]+)+)\s*(?:[—–-]+|\.)\s+(.+)$"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
# Поле карточки во всех встреченных видах: "- **id**: v", "**id:** v", "**id.** v", "**id**".
FIELD_RE = re.compile(r"^\s*(?:[-*+]\s+)?\*\*([a-z_]+)\s*[:.]?\s*\*\*\s*[:.]?\s*(.*)$")
# Семь семей записали карточку двухколоночной таблицей: "| `id` | значение |".
TABLE_FIELD_RE = re.compile(r"^\s*\|\s*`?([a-z_]+)`?\s*\|(.*?)\|?\s*$")
# Шапка и разделитель такой таблицы — служебные строки, в текст карточки они не идут.
TABLE_HEAD_RE = re.compile(r"^\s*\|\s*(?:поле|field|параметр)\s*\|", re.IGNORECASE)
TABLE_RULE_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

FIELD_ORDER = [
    "one_liner", "buyer", "players", "money", "pricing", "moat", "capital",
    "time_to_revenue", "foreign_dependency", "ru_analog", "ru_fit", "kill_switch", "failures",
]
FIELD_LABEL = {
    "one_liner": "Суть",
    "buyer": "Кто платит",
    "players": "Игроки",
    "money": "Деньги",
    "pricing": "Цена и модель оплаты",
    "moat": "Что защищает",
    "capital": "Капиталоёмкость",
    "time_to_revenue": "Когда первый платёж",
    "foreign_dependency": "Зависимость от зарубежного",
    "ru_analog": "Российский аналог",
    "ru_fit": "Что ломается в России",
    "kill_switch": "Что убьёт идею",
    "failures": "Кто пробовал и закрылся",
}
FAMILY_TITLE_RE = re.compile(r"^#\s+(?:Семья\s+)?([0-9AB]+)[.:]?\s*(.*)$")
# Имена полей, по которым строка таблицы опознаётся как поле, а не как содержательная таблица.
KNOWN_FIELDS = frozenset(FIELD_ORDER) | {"id", "name", "family"}

# Служебная диагностика инструментов, которой не место в отчёте для читателя.
NOISE_RE = re.compile(
    r"(?:[^.;\n]*?(?:квота\s+WebSearch|WebSearch[^.;\n]{0,20}исчерпан|lite\.duckduckgo[^.;\n]{0,40}HTTP\s*000"
    r"|HTTP\s*000|200/200|через\s+WebFetch|WebFetch\s+(?:отдал|дважды|вернул)|в\s+этой\s+сессии)[^.;\n]*[.;]?)",
    re.IGNORECASE,
)

# Имена инструментов вырезаем точечно, чтобы сохранить стоящие рядом ссылки и даты.
TOOLWORD_RE = re.compile(
    r"\b(?:WebFetch|WebSearch|ToolSearch|MCP\s+brave[-\s]?search|brave[-\s]search|"
    r"(?:lite\.|html\.)?duckduckgo(?:\.com)?)\b\s*:?\s*",
    re.IGNORECASE,
)

VERDICTS = ("занято", "частично", "свободно", "нет данных")


def derive_verdict(ru_analog: str) -> str:
    """Нормализует вердикт по России из свободного текста поля ru_analog."""
    low = ru_analog.lower().lstrip("*_ ")
    for v in ("частично", "занято", "свободно"):
        if low.startswith(v):
            return v
    if low.startswith(("есть", "да,")):
        return "занято"
    if low.startswith(("нет,", "нет —", "нет.", "отсутств")):
        return "свободно"
    for v in ("частично", "занято", "свободно"):
        if v in low[:120]:
            return v
    return "нет данных"


PROVERKA_VERDICT_RE = re.compile(r"стало\s+«([^»]+)»")


def card_verdict(value: str) -> str:
    """Вердикт, зафиксированный полем `ru_verdict` карточки, — главный источник."""
    v = (value or "").strip().lower().rstrip(".")
    return v if v in VERDICTS else ""


def verdict_from_proverka(proverka: str) -> str:
    """Вердикт, установленный адверсариальной проверкой; он главнее исходного текста карточки."""
    m = PROVERKA_VERDICT_RE.search(proverka or "")
    if not m:
        return ""
    value = m.group(1).strip().lower().rstrip(".")
    return value if value in VERDICTS else ""


def strip_noise(text: str) -> str:
    """Убирает предложения про квоты и коды ответа инструментов."""
    cleaned = NOISE_RE.sub("", text)
    cleaned = TOOLWORD_RE.sub("", cleaned)               # имя инструмента убираем, ссылку рядом оставляем
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)          # переводы строк сохраняем
    cleaned = re.sub(r"[ \t]+([.;,])", r"\1", cleaned)
    return cleaned.strip(" \t;,")


# --------------------------------------------------------------------------- markdown


def inline(md: str) -> str:
    """Переводит строчную разметку в HTML: код, ссылки, полужирный, курсив."""
    out = html.escape(md, quote=False)
    out = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", out)
    out = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener">{m.group(1)}</a>',
        out,
    )
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", out)
    out = re.sub(
        r"(?<![\">/\w])(https?://[^\s<>\"]+)",
        lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noopener">{m.group(1)}</a>',
        out,
    )
    return linkify_domains(out)


# Голые домены («players: coinkyt.com, bitok.org») — на телефоне по ним надо нажимать.
TLD = ("com|ru|io|ai|org|net|co|dev|app|tech|me|so|cloud|pro|info|biz|su|by|kz|ua|uk|de|fr|eu|xyz"
       "|online|site|store|tv|sh|to|link|team|solutions|works|group|digital|finance|legal|law"
       "|health|systems|network|studio|agency|expert|capital|fund|vc|cc|is|it|es|pl|nl|se|fi|no")
DOMAIN_RE = re.compile(
    r"(?<![\w@/.>-])((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:" + TLD + r"))(?![\w.-])"
    r"(/[^\s,;)\"<]*)?",
    re.IGNORECASE,
)
SAFE_SPLIT_RE = re.compile(r"(<a\b[^>]*>.*?</a>|<code>.*?</code>)", re.DOTALL | re.IGNORECASE)


def linkify_domains(fragment: str) -> str:
    """Оборачивает голые домены в ссылки, не трогая уже готовые ссылки и код."""
    parts = SAFE_SPLIT_RE.split(fragment)
    for i, part in enumerate(parts):
        if i % 2:  # это уже ссылка или код — не трогаем
            continue
        parts[i] = DOMAIN_RE.sub(
            lambda m: '<a href="https://{0}{1}" target="_blank" rel="noopener">{0}{1}</a>'.format(
                m.group(1), m.group(2) or ""
            ),
            part,
        )
    return "".join(parts)


def plain(md: str, limit: int = 0) -> str:
    """Markdown или HTML в простой текст: для строк списка и поисковой строки."""
    t = re.sub(r"<[^>]+>", " ", md)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[*`_>#|]+", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip(" -–—")
    return t[:limit].rstrip() if limit and len(t) > limit else t


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def render_table(rows: list[list[str]]) -> str:
    """Таблица либо остаётся таблицей, либо разворачивается в блоки.

    Порог 180 знаков в ячейке: шире этого таблица на телефоне нечитаема,
    поэтому каждая строка становится блоком «метка — значение».
    """
    if not rows:
        return ""
    head, body = rows[0], rows[1:]
    widest = max((len(c) for r in rows for c in r), default=0)
    if widest <= 180:
        th = "".join(f"<th>{inline(c)}</th>" for c in head)
        trs = "".join(
            "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body
        )
        return f'<div class="tablewrap"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'
    # Широкая таблица на телефоне разворачивается в раскрывающиеся блоки: иначе
    # документ вырастает до сотен тысяч пикселей и пролистать его невозможно.
    blocks = []
    for r in body:
        first = inline(r[0]) if r else ""
        preview = plain(r[1], 90) if len(r) > 1 else ""
        rest = "".join(
            f'<div class="rowfield"><span class="rowlabel">{inline(head[i]) if i < len(head) else ""}</span>'
            f'<div class="rowvalue">{inline(c)}</div></div>'
            for i, c in enumerate(r[1:], start=1)
            if c
        )
        blocks.append(
            '<details class="rowcard"><summary><span class="rowhead">' + first + "</span>"
            + (f'<span class="rowpreview">{html.escape(preview)}</span>' if preview else "")
            + "</summary>" + rest + "</details>"
        )
    return '<div class="rowcards">' + "".join(blocks) + "</div>"


def markdown(md: str) -> str:
    """Блочный markdown в HTML: заголовки, списки, таблицы, цитаты, абзацы."""
    lines = md.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if re.match(r"^\s*(?:---+|\*\*\*+|___+)\s*$", line):
            out.append("<hr>")
            i += 1
            continue
        m = HEADING_RE.match(line)
        if m:
            lvl = min(len(m.group(1)) + 1, 6)
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if line.lstrip().startswith("|") and "|" in line:
            rows = []
            while i < n and lines[i].lstrip().startswith("|"):
                if not re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i]):
                    rows.append(split_row(lines[i]))
                i += 1
            out.append(render_table(rows))
            continue
        if re.match(r"^\s*>", line):
            buf = []
            while i < n and re.match(r"^\s*>", lines[i]):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f"<blockquote>{markdown(chr(10).join(buf))}</blockquote>")
            continue
        m = re.match(r"^\s*(\d+)[.)]\s+(.*)$", line)
        if m:
            items = []
            while i < n:
                mm = re.match(r"^\s*\d+[.)]\s+(.*)$", lines[i])
                if not mm:
                    if lines[i].startswith(("  ", "\t")) and lines[i].strip() and items:
                        items[-1] += " " + lines[i].strip()
                        i += 1
                        continue
                    break
                items.append(mm.group(1))
                i += 1
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
            continue
        if re.match(r"^\s*[-*+]\s+", line):
            items = []
            while i < n:
                mm = re.match(r"^\s*[-*+]\s+(.*)$", lines[i])
                if not mm:
                    if lines[i].startswith(("  ", "\t")) and lines[i].strip() and items:
                        items[-1] += " " + lines[i].strip()
                        i += 1
                        continue
                    break
                items.append(mm.group(1))
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue
        buf = []
        while i < n and lines[i].strip() and not HEADING_RE.match(lines[i]) \
                and not lines[i].lstrip().startswith(("|", ">")) \
                and not re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        if buf:
            out.append(f"<p>{inline(' '.join(buf))}</p>")
    return "".join(out)


# --------------------------------------------------------------------------- разбор


@dataclass
class Card:
    id: str
    name: str
    family: str
    fields: dict = dc_field(default_factory=dict)
    notes: str = ""


@dataclass
class Family:
    code: str
    title: str
    file: str
    intro_md: str = ""
    appendix_md: str = ""
    cards: list = dc_field(default_factory=list)


def parse_family(path: Path) -> Family:
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    code = path.name.split("-", 1)[0]
    title = ""
    for line in lines[:6]:
        m = FAMILY_TITLE_RE.match(line)
        if m:
            code, title = m.group(1), m.group(2).strip()
            break
    if not title:
        title = path.stem.split("-", 1)[-1].replace("-", " ")

    fam = Family(code=code, title=title, file=path.name)

    # Границы блоков по заголовкам.
    marks = [(i, HEADING_RE.match(l)) for i, l in enumerate(lines)]
    marks = [(i, m) for i, m in marks if m]
    bounds = [i for i, _ in marks] + [len(lines)]

    first_card_at = None
    intro_chunks, appendix_chunks = [], []
    for idx, (start, _m) in enumerate(marks):
        end = bounds[idx + 1]
        block = lines[start:end]
        cm = CARD_RE.match(block[0])
        if cm:
            if first_card_at is None:
                first_card_at = start
            fam.cards.append(parse_card(cm.group(1), cm.group(2).strip(), fam.code, block[1:]))
        elif first_card_at is None:
            intro_chunks.append("\n".join(block))
        else:
            appendix_chunks.append("\n".join(block))

    if first_card_at is None:  # ни одной карточки не распознали — весь файл во вступление
        intro_chunks = ["\n".join(lines)]

    fam.intro_md = "\n\n".join(intro_chunks).strip()
    fam.appendix_md = "\n\n".join(appendix_chunks).strip()
    return fam


def parse_card(cid: str, name: str, fam_code: str, body: list[str]) -> Card:
    """Собирает поля карточки, сохраняя многострочные значения как markdown."""
    raw: dict[str, list[str]] = {}
    notes: list[str] = []
    current: str | None = None
    for line in body:
        m = FIELD_RE.match(line)
        if not m:
            tm = TABLE_FIELD_RE.match(line)
            if tm and tm.group(1) in KNOWN_FIELDS:
                m = tm
        if m:
            current = m.group(1)
            raw.setdefault(current, [])
            if m.group(2).strip():
                raw[current].append(m.group(2).strip())
            continue
        if re.match(r"^\s*(?:---+|\*\*\*+)\s*$", line):
            current = None
            continue
        # Шапка и разделитель таблицы полей стоят до первого поля; внутри значения
        # такие же строки могут быть настоящей таблицей, поэтому режем только снаружи.
        if current is None and (TABLE_HEAD_RE.match(line) or TABLE_RULE_RE.match(line)):
            continue
        if current is not None:
            raw[current].append(line.rstrip())
            continue
        if line.strip():
            notes.append(line)

    fields = {k: "\n".join(v).strip() for k, v in raw.items() if "\n".join(v).strip()}
    family = (fields.pop("family", "") or fam_code).split()
    return Card(
        id=fields.pop("id", cid) or cid,
        name=fields.pop("name", "") or name,
        family=family[0].strip(".,") if family else fam_code,
        fields=fields,
        notes="\n".join(notes).strip(),
    )


def render_value(md: str) -> str:
    """Однострочное значение — строчной разметкой, многострочное или список — блочной."""
    stripped = md.strip()
    if "\n" in stripped or re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|\|)", stripped):
        return markdown(stripped)
    return inline(stripped)


# --------------------------------------------------------------------------- сборка


def build() -> None:
    families = [parse_family(p) for p in sorted(CATALOG.glob("families/*.md"))]
    families.sort(key=lambda f: (int(re.sub(r"\D", "", f.code) or 0), f.code))

    verdict_by_id: dict[str, str] = {}
    key_by_id: dict[str, str] = {}
    idx_path = CATALOG / "data" / "index.json"
    if idx_path.exists():
        for fam in json.loads(idx_path.read_text(encoding="utf-8")):
            for it in fam.get("ideas") or []:
                if it.get("ru"):
                    verdict_by_id[it["id"]] = it["ru"]
                if it.get("key_number"):
                    key_by_id[it["id"]] = it["key_number"]

    ideas, fam_out, fam_cards = [], [], {}
    for fam in families:
        cards = []
        for c in fam.cards:
            verdict = (
                card_verdict(c.fields.get("ru_verdict", ""))
                or verdict_from_proverka(c.fields.get("proverka", ""))
                or verdict_by_id.get(c.id)
                or derive_verdict(c.fields.get("ru_analog", ""))
            )
            rendered = {}
            for k, v in c.fields.items():
                v = strip_noise(v)
                if v:
                    rendered[k] = render_value(v)
            card = {
                "id": c.id,
                "name": c.name,
                "family": fam.code,
                "family_title": fam.title,
                "verdict": verdict,
                "key_number": inline(strip_noise(key_by_id.get(c.id, ""))),
                "fields": rendered,
                "notes": markdown(strip_noise(c.notes)) if c.notes else "",
            }
            cards.append(card)
            # В общий список идёт только лёгкая часть: полные поля лежат в файле семьи.
            ideas.append({
                "id": card["id"], "name": card["name"], "family": card["family"],
                "family_title": card["family_title"], "verdict": card["verdict"],
                "duplicate": bool(c.fields.get("duplicate_of")),
                # В списке — только текст: строка обёрнута в ссылку, вложенные ссылки недопустимы.
                "one_liner": plain(card["fields"].get("one_liner", ""), 240),
                "key_number": plain(card["key_number"], 150),
                "search": " ".join([
                    c.id, plain(c.name), plain(c.fields.get("one_liner", ""), 200),
                    plain(c.fields.get("players", ""), 220),
                    plain(c.fields.get("ru_analog", ""), 200), plain(fam.title),
                ]).lower(),
            })
        fam_cards[fam.code] = {
            "code": fam.code,
            "title": fam.title,
            "cards": cards,
            "intro": markdown(strip_noise(fam.intro_md)),
            "appendix": markdown(strip_noise(fam.appendix_md)),
        }
        fam_out.append({
            "code": fam.code,
            "title": fam.title,
            "file": fam.file,
            "count": len(cards),
        })

    docs = []
    for name, title in [
        ("README.md", "О исследовании"),
        ("40-proverka.md", "Проверка скептиков"),
        ("90-provaly.md", "Провалы и закрытия"),
        ("99-neproverennoe.md", "Что не проверено"),
    ]:
        p = CATALOG / name
        if p.exists():
            docs.append({
                "slug": name.replace(".md", ""),
                "title": title,
                "html": markdown(strip_noise(p.read_text(encoding="utf-8"))),
            })

    DOCS.mkdir(exist_ok=True)
    (DOCS / "data").mkdir(exist_ok=True)
    counts = {v: sum(1 for i in ideas if i["verdict"] == v) for v in VERDICTS}
    # Часть идей записана в двух-трёх семьях сразу; в счёт различимых идёт основная карточка.
    distinct = sum(1 for i in ideas if not i["duplicate"])

    (DOCS / "data" / "list.json").write_text(
        json.dumps({"ideas": ideas, "families": fam_out, "counts": counts,
                    "total": len(ideas), "distinct": distinct},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    fam_dir = DOCS / "data" / "family"
    fam_dir.mkdir(exist_ok=True)
    for code, payload in fam_cards.items():
        (fam_dir / f"{code}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    for d in docs:
        (DOCS / "data" / f"{d['slug']}.json").write_text(
            json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    (DOCS / "data" / "docs.json").write_text(
        json.dumps([{"slug": d["slug"], "title": d["title"]} for d in docs], ensure_ascii=False),
        encoding="utf-8",
    )

    for asset in ASSETS.iterdir():
        shutil.copy2(asset, DOCS / asset.name)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    print(f"семей: {len(fam_out)}  карточек: {len(ideas)}  различимых идей: {distinct}")
    print("вердикты:", counts)
    for f in fam_out:
        if f["count"] == 0:
            print(f"  ВНИМАНИЕ: в семье {f['code']} не распознано ни одной карточки ({f['file']})")
    files = [p for p in (DOCS / "data").rglob("*.json")]
    total = sum(p.stat().st_size for p in files)
    first = (DOCS / "data" / "list.json").stat().st_size
    biggest = max(fam_dir.glob("*.json"), key=lambda p: p.stat().st_size)
    print(f"данных: {total/1024:.0f} КБ в {len(files)} файлах")
    print(f"первая загрузка: list.json {first/1024:.0f} КБ; "
          f"самый большой файл семьи — {biggest.name} {biggest.stat().st_size/1024:.0f} КБ")


if __name__ == "__main__":
    build()
