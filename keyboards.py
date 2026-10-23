from typing import Literal
from urllib.parse import urlencode

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class CelebrityCallback(CallbackData, prefix="celebs"):
    category: Literal["day", "sign", "search", "today"]
    session: str
    offset: int = -1


class ActionCallback(CallbackData, prefix="action"):
    action: Literal["menu", "ai", "quiz", "card", "stats", "change", "today"]
    session: str


class QuizCallback(CallbackData, prefix="quiz"):
    session: str
    round: str
    answer: int


def action_button(
    text: str, action: str, session: str
) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=ActionCallback(action=action, session=session).pack(),
    )


def menu_keyboard(session: str) -> InlineKeyboardMarkup:
    rows = []
    for category, label in [
        ("day", "Знаменитости в этот день"),
        ("sign", "Знаменитости этого знака"),
    ]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=CelebrityCallback(
                        category=category, session=session
                    ).pack(),
                )
            ]
        )
    rows.extend(
        [
            [
                action_button("💬 Спросить AI", "ai", session),
                action_button("🎯 Угадай знак", "quiz", session),
            ],
            [
                action_button("🪪 Моя карточка", "card", session),
                action_button("🎂 Сегодня", "today", session),
            ],
            [
                action_button("📊 Мой результат", "stats", session),
                action_button("✏️ Другая дата", "change", session),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_keyboard(session: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[action_button("← Главное меню", "menu", session)]]
    )


def pagination_keyboard(
    category: str, session: str, offset: int, menu_session: str | None = None
) -> InlineKeyboardMarkup:
    labels = {
        "day": "день",
        "sign": "знак",
        "search": "поиск",
        "today": "сегодня",
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Показать еще ({labels[category]})",
                    callback_data=CelebrityCallback(
                        category=category, session=session, offset=offset
                    ).pack(),
                )
            ],
            [action_button("← Главное меню", "menu", menu_session or session)],
        ]
    )


def quiz_keyboard(quiz: dict, session: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=sign,
            callback_data=QuizCallback(
                session=session, round=quiz["round"], answer=index
            ).pack(),
        )
        for index, sign in enumerate(quiz["options"])
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            buttons[:2],
            buttons[2:],
            [action_button("← Главное меню", "menu", session)],
        ]
    )


def quiz_result_keyboard(session: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [action_button("Ещё вопрос →", "quiz", session)],
            [action_button("← Главное меню", "menu", session)],
        ]
    )


def share_keyboard(
    session: str, username: str, text: str
) -> InlineKeyboardMarkup:
    keyboard = back_keyboard(session)
    if username:
        url = "https://t.me/share/url?" + urlencode(
            {
                "url": f"https://t.me/{username}",
                "text": text,
            }
        )
        keyboard.inline_keyboard.insert(
            0, [InlineKeyboardButton(text="↗️ Поделиться с друзьями", url=url)]
        )
    return keyboard
