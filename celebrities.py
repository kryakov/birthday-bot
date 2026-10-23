import json
import re
import unicodedata
from html import escape
from pathlib import Path
from typing import NotRequired, TypedDict


class Celebrity(TypedDict):
    id: str
    first_name: str
    last_name: str
    day: int
    month: int
    zodiac: str
    description: str
    category: str
    aliases: list[str]
    source: str
    birthday_source: NotRequired[str]
    nickname: NotRequired[str]


PAGE_SIZE = 3
CATEGORY_NAMES = {
    "all": "Все",
    "music": "Музыка",
    "blog": "Блогеры",
    "screen": "Кино и сериалы",
    "sport": "Спорт",
}
CATALOG_PATH = Path(__file__).with_name("data") / "celebrities.json"
CELEBRITIES: list[Celebrity] = json.loads(
    CATALOG_PATH.read_text(encoding="utf-8")
)


def display_name(person: Celebrity) -> str:
    return person.get("nickname") or (
        f"{person['first_name']} {person['last_name']}".strip()
    )


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold().replace("ё", "е"))
    return " ".join(re.findall(r"[a-zа-я0-9]+", text))


def search_catalog(
    query: str = "",
    sign: str = "",
    day: int = 0,
    month: int = 0,
    category: str = "all",
) -> list[Celebrity]:
    words = normalize(query).split()
    matches = []
    for person in CELEBRITIES:
        if sign and person["zodiac"] != sign:
            continue
        if day and person["day"] != day:
            continue
        if month and person["month"] != month:
            continue
        if category != "all" and person["category"] != category:
            continue
        names = " ".join(
            [
                display_name(person),
                person["first_name"],
                person["last_name"],
                *person["aliases"],
            ]
        )
        searchable = normalize(names + " " + person["description"])
        if words and not all(word in searchable for word in words):
            continue
        matches.append(person)
    return matches


def get_celebrities_by_day(
    day: int, month: int, offset: int = 0
) -> list[Celebrity]:
    if offset < 0:
        raise ValueError("Смещение не может быть отрицательным")
    return search_catalog(day=day, month=month)[offset : offset + PAGE_SIZE]


def get_celebrities_by_sign(sign: str, offset: int = 0) -> list[Celebrity]:
    if offset < 0:
        raise ValueError("Смещение не может быть отрицательным")
    return search_catalog(sign=sign)[offset : offset + PAGE_SIZE]


def format_celebrities(people: list[Celebrity], offset: int = 0) -> str:
    entries = []
    for number, person in enumerate(people, start=offset + 1):
        entries.append(
            f"<b>{number}. {escape(display_name(person))}</b>\n"
            f"{person['day']:02d}.{person['month']:02d} · "
            f"{person['zodiac']} · {CATEGORY_NAMES[person['category']]}\n"
            f"{escape(person['description'])}\n"
            f'<a href="{escape(person["source"], quote=True)}">Источник</a>'
        )
    return "\n\n".join(entries)
