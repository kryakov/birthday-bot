import random
from datetime import date, datetime
from html import escape
from secrets import token_hex
from zoneinfo import ZoneInfo

from celebrities import CELEBRITIES, display_name, search_catalog
from zodiac import ZODIAC_DESCRIPTIONS

ZODIAC_EMOJI = {
    "Овен": "♈",
    "Телец": "♉",
    "Близнецы": "♊",
    "Рак": "♋",
    "Лев": "♌",
    "Дева": "♍",
    "Весы": "♎",
    "Скорпион": "♏",
    "Стрелец": "♐",
    "Козерог": "♑",
    "Водолей": "♒",
    "Рыбы": "♓",
}


def today() -> date:
    return datetime.now(ZoneInfo("Europe/Moscow")).date()


def days_until_birthday(
    day: int, month: int, current: date | None = None
) -> int:
    current = current or today()
    for year in range(current.year, current.year + 9):
        try:
            birthday = date(year, month, day)
        except ValueError:
            continue
        if birthday >= current:
            return (birthday - current).days
    raise ValueError("Не удалось определить следующий день рождения")


def profile_text(data: dict) -> str:
    day, month, sign = data["day"], data["month"], data["sign"]
    remaining = days_until_birthday(day, month)
    countdown = "Сегодня твой день. С днём рождения! 🎉"
    if remaining:
        countdown = f"До следующего {day:02d}.{month:02d}: {remaining} дн."
    same_day = len(search_catalog(day=day, month=month))
    same_sign = len(search_catalog(sign=sign))
    return (
        f"{ZODIAC_EMOJI[sign]} <b>{sign} · {day:02d}.{month:02d}</b>\n"
        f"{countdown}\n\n{ZODIAC_DESCRIPTIONS[sign]}\n\n"
        f"🎂 В твой день: <b>{same_day}</b>\n"
        f"✨ Твой знак: <b>{same_sign}</b>\n\n"
        "Выбирай подборку, задай вопрос AI или проверь себя в викторине."
    )


def share_text(data: dict) -> str:
    sign = data["sign"]
    people = search_catalog(day=data["day"], month=data["month"])
    label = "Со мной в один день родились"
    if not people:
        people = search_catalog(sign=sign)
        label = "Мой знак делят"
    names = ", ".join(display_name(p) for p in people[:3])
    return (
        f"МОЙ ЗВЁЗДНЫЙ ДЕНЬ ✨\n\n"
        f"{data['day']:02d}.{data['month']:02d} · "
        f"{ZODIAC_EMOJI[sign]} {sign}\n"
        f"{label}: {names}.\n\n"
        "А кто твой звёздный сосед? Проверь свой день рождения!"
    )


def make_quiz(previous_ids: list[str] | None = None) -> dict:
    unseen = [p for p in CELEBRITIES if p["id"] not in (previous_ids or [])]
    person = random.choice(unseen or CELEBRITIES)
    options = random.sample(
        [sign for sign in ZODIAC_DESCRIPTIONS if sign != person["zodiac"]], 3
    )
    options.append(person["zodiac"])
    random.shuffle(options)
    return {
        "round": token_hex(3),
        "person_id": person["id"],
        "name": display_name(person),
        "day": person["day"],
        "month": person["month"],
        "options": options,
        "correct": options.index(person["zodiac"]),
    }


def quiz_text(quiz: dict) -> str:
    return (
        "🎯 <b>Угадай знак</b>\n\n"
        f"{escape(quiz['name'])}\n"
        f"День рождения: <b>{quiz['day']:02d}.{quiz['month']:02d}</b>\n\n"
        "Какой у этого человека знак зодиака?"
    )
