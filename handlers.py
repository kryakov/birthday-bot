import re
from html import escape
from pathlib import Path
from secrets import token_hex

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.chat_action import ChatActionSender

from assistant import AIBusy, LlamaAssistant
from celebrities import (
    CELEBRITIES,
    PAGE_SIZE,
    format_celebrities,
    search_catalog,
)
from experience import make_quiz, profile_text, quiz_text, share_text, today
from keyboards import (
    ActionCallback,
    CelebrityCallback,
    QuizCallback,
    back_keyboard,
    menu_keyboard,
    pagination_keyboard,
    quiz_keyboard,
    quiz_result_keyboard,
    share_keyboard,
)
from storage import ProfileStore
from zodiac import get_zodiac_sign, validate_birth_date

EMPTY_MESSAGE = "Больше знаменитостей в базе нет!"
ARTWORK = Path(__file__).with_name("assets") / "star-day.png"


async def set_birthday(state: FSMContext, day: int, month: int) -> dict:
    data = {
        "day": day,
        "month": month,
        "sign": get_zodiac_sign(day, month),
        "session": token_hex(4),
        "day_offset": 0,
        "sign_offset": 0,
        "today_offset": 0,
        "search_offset": 0,
    }
    await state.set_data(data)
    return data


async def welcome(message: Message, text: str, keyboard=None) -> None:
    if ARTWORK.is_file():
        await message.answer_photo(
            FSInputFile(ARTWORK), caption=text, reply_markup=keyboard
        )
    else:
        await message.answer(text, reply_markup=keyboard)


async def start(
    message: Message, state: FSMContext, profiles: ProfileStore
) -> None:
    await state.clear()
    saved = profiles.get(message.from_user.id)
    if saved:
        data = await set_birthday(state, saved["day"], saved["month"])
        await welcome(
            message,
            "✨ <b>С возвращением в «Звёздный день»!</b>\n\n"
            + profile_text(data),
            menu_keyboard(data["session"]),
        )
        return
    await welcome(
        message,
        "✨ <b>ЗВЁЗДНЫЙ ДЕНЬ</b>\n"
        "У каждого дня — свои звёзды. Найди своих.\n\n"
        f"Внутри {len(CELEBRITIES)} знаменитостей, локальный AI "
        "и викторина для тех, кто знает больше, чем кажется.\n\n"
        "<b>Когда ты родился?</b> Напиши дату в формате ДД.ММ, без года. "
        "Например: <code>26.06</code>.",
    )


async def help_command(message: Message) -> None:
    await message.answer(
        "<b>Как тут всё устроено</b>\n\n"
        "🎂 Введи дату ДД.ММ: получишь две независимые подборки.\n"
        "💬 Напиши «актёры моего знака», «Влад А4» или «кто родился 09.03».\n"
        "🎯 Угадывай знаки, набирай баллы и сравнивай результаты с друзьями.\n"
        "🪪 Забери карточку своего дня рождения и перешли в чат группы.\n\n"
        "/menu — главное меню\n/search имя — поиск по каталогу\n"
        "/ai — состояние AI\n/quiz — новый вопрос\n/card — моя карточка\n"
        "/forget — удалить дату и счёт\n/start — начать подборки заново\n\n"
        "Даты берутся из каталога со ссылками на источники. AI работает "
        "через локальную Ollama; он может неверно понять запрос. "
        "Гороскопные характеристики — развлечение. "
        "На компьютере сохраняются только Telegram ID, день, месяц и счёт."
    )


async def ensure_profile(
    message: Message, state: FSMContext, profiles: ProfileStore
) -> dict | None:
    data = await state.get_data()
    if data.get("session"):
        return data
    saved = profiles.get(message.from_user.id)
    if saved:
        return await set_birthday(state, saved["day"], saved["month"])
    await message.answer(
        "Сначала введи дату рождения: ДД.ММ. Например: 26.06."
    )
    return None


async def menu(
    message: Message, state: FSMContext, profiles: ProfileStore
) -> None:
    if data := await ensure_profile(message, state, profiles):
        await state.update_data(mode=None)
        await message.answer(
            profile_text(data), reply_markup=menu_keyboard(data["session"])
        )


async def receive_message(
    message: Message,
    state: FSMContext,
    profiles: ProfileStore,
    assistant: LlamaAssistant,
) -> None:
    text = message.text
    if text and text.startswith("/"):
        await message.answer("Такой команды нет. Список команд — /help.")
        return
    if birthday := validate_birth_date(text):
        day, month = birthday
        profiles.save_birthday(message.from_user.id, day, month)
        data = await set_birthday(state, day, month)
        await message.answer(
            profile_text(data), reply_markup=menu_keyboard(data["session"])
        )
        return
    data = await state.get_data()
    looks_like_date = text and re.fullmatch(r"[0-9./\s-]+", text)
    if not text or not data.get("session") or looks_like_date:
        await message.answer(
            "Не получилось распознать дату. Введи существующую дату "
            "в формате ДД.ММ, без года. Например: 09.03."
        )
        return
    await answer_question(message, state, assistant, text)


async def answer_question(
    message: Message,
    state: FSMContext,
    assistant: LlamaAssistant,
    question: str,
) -> None:
    data = await state.get_data()
    if len(question) > 600:
        await message.answer("Сократи вопрос до 600 символов, пожалуйста.")
        return
    await message.answer("💬 Смотрю каталог…")
    try:
        async with ChatActionSender(
            bot=message.bot, chat_id=message.chat.id, action=ChatAction.TYPING
        ):
            reply = await assistant.ask(question, data)
    except AIBusy:
        await message.answer(
            "AI занят другим вопросом. Попробуй через несколько секунд. "
            "Подборки и викторина доступны в /menu."
        )
        return
    footer = ""
    if not reply.used_ai:
        footer = "\n\n<i>AI недоступен. Показан обычный поиск по каталогу.</i>"
    if not reply.people:
        await message.answer(
            reply.text + footer, reply_markup=back_keyboard(data["session"])
        )
        return
    session = token_hex(4)
    all_people = reply.people
    await state.update_data(
        search_ids=[p["id"] for p in all_people],
        search_session=session,
        search_offset=0,
    )
    page = all_people[:PAGE_SIZE]
    await message.answer(
        "💬 <b>Нашлось в каталоге</b>\n\n"
        f"{reply.text}\n\n{format_celebrities(page)}{footer}",
        reply_markup=pagination_keyboard(
            "search", session, len(page), data["session"]
        ),
    )
    await state.update_data(search_offset=len(page))


async def search_command(
    message: Message,
    state: FSMContext,
    profiles: ProfileStore,
    assistant: LlamaAssistant,
) -> None:
    if not await ensure_profile(message, state, profiles):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Напиши, например: /search Билли Айлиш")
        return
    await answer_question(message, state, assistant, parts[1])


async def ai_command(message: Message, assistant: LlamaAssistant) -> None:
    available = await assistant.status()
    text = "🟢 AI на связи" if available else "🟡 AI сейчас недоступен"
    await message.answer(
        f"<b>{text}</b>\n\n"
        "Я умею искать по каталогу: «блогеры моего знака», «Билли Айлиш», "
        "«актёры, родившиеся в июне». Напиши вопрос обычным сообщением.\n\n"
        "Если AI недоступен, проверь, что Ollama запущена на компьютере. "
        "Обычный поиск и кнопки работают без неё."
    )


async def forget(
    message: Message, state: FSMContext, profiles: ProfileStore
) -> None:
    profiles.forget(message.from_user.id)
    await state.clear()
    await message.answer(
        "Дата рождения и счёт удалены. Для нового знакомства — /start."
    )


async def send_page(
    callback: CallbackQuery,
    callback_data: CelebrityCallback,
    state: FSMContext,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Открой личный чат с ботом.")
        return
    data = await state.get_data()
    category = callback_data.category
    expected = data.get(
        "search_session" if category == "search" else "session"
    )
    if expected != callback_data.session:
        await callback.answer(
            "Эти кнопки устарели. Открой /menu.", show_alert=True
        )
        return
    offset_key = f"{category}_offset"
    offset = data.get(offset_key, 0)
    if callback_data.offset not in (-1, offset):
        await callback.answer(
            "Эта страница уже показана. Используй последнюю подборку."
        )
        return
    if category == "day":
        people = search_catalog(day=data["day"], month=data["month"])
        title = f"🎂 <b>Родились {data['day']:02d}.{data['month']:02d}</b>"
    elif category == "sign":
        people = search_catalog(sign=data["sign"])
        title = f"✨ <b>Знаменитости знака {data['sign']}</b>"
    elif category == "today":
        current = today()
        if data.get("today_date") != current.isoformat():
            await callback.answer(
                "Наступил новый день. Открой «Сегодня» в меню."
            )
            return
        people = search_catalog(day=current.day, month=current.month)
        title = "🎂 <b>Сегодня празднуют</b>"
    else:
        by_id = {p["id"]: p for p in CELEBRITIES}
        people = [
            by_id[key] for key in data.get("search_ids", []) if key in by_id
        ]
        title = "🔎 <b>Результаты поиска</b>"
    await callback.answer()
    page = people[offset : offset + PAGE_SIZE]
    if not page:
        await callback.message.answer(
            EMPTY_MESSAGE, reply_markup=menu_keyboard(data["session"])
        )
        return
    next_offset = offset + len(page)
    await callback.message.answer(
        f"{title}\nПоказано {offset + 1}–{next_offset} из {len(people)}\n\n"
        f"{format_celebrities(page, offset)}",
        reply_markup=pagination_keyboard(
            category, expected, next_offset, data["session"]
        ),
    )
    await state.update_data({offset_key: next_offset})


async def celebrities_by_day(
    callback: CallbackQuery,
    callback_data: CelebrityCallback,
    state: FSMContext,
) -> None:
    await send_page(callback, callback_data, state)


async def celebrities_by_sign(
    callback: CallbackQuery,
    callback_data: CelebrityCallback,
    state: FSMContext,
) -> None:
    await send_page(callback, callback_data, state)


async def send_quiz(message: Message, state: FSMContext, data: dict) -> None:
    quiz = make_quiz(data.get("quiz_seen", []))
    seen = [*data.get("quiz_seen", []), quiz["person_id"]][-len(CELEBRITIES) :]
    await message.answer(
        quiz_text(quiz), reply_markup=quiz_keyboard(quiz, data["session"])
    )
    await state.update_data(quiz=quiz, quiz_seen=seen)


async def quiz_command(
    message: Message, state: FSMContext, profiles: ProfileStore
) -> None:
    if data := await ensure_profile(message, state, profiles):
        await send_quiz(message, state, data)


async def answer_quiz(
    callback: CallbackQuery,
    callback_data: QuizCallback,
    state: FSMContext,
    profiles: ProfileStore,
) -> None:
    data = await state.get_data()
    quiz = data.get("quiz")
    if (
        not quiz
        or data.get("session") != callback_data.session
        or quiz["round"] != callback_data.round
    ):
        await callback.answer("Этот вопрос уже закрыт. Нажми «Ещё вопрос».")
        return
    if callback_data.answer not in range(4):
        await callback.answer("Выбери один из четырёх вариантов.")
        return
    correct = callback_data.answer == quiz["correct"]
    await callback.answer(
        "Верно! 🎉" if correct else "Почти! Ответ — в сообщении ниже."
    )
    await state.update_data(quiz=None)
    score = profiles.record_answer(callback.from_user.id, correct)
    sign = quiz["options"][quiz["correct"]]
    await callback.message.answer(
        f"{'🎉 Верно!' if correct else '🪐 В этот раз не угадал.'}\n\n"
        f"<b>{escape(quiz['name'])}</b> — {sign}.\n"
        f"Дата: {quiz['day']:02d}.{quiz['month']:02d}\n\n"
        f"Твой счёт: <b>{score['correct']} из {score['played']}</b>",
        reply_markup=quiz_result_keyboard(data["session"]),
    )


async def send_card(message: Message, data: dict, bot_username: str) -> None:
    text = share_text(data)
    await welcome(
        message,
        escape(text),
        share_keyboard(data["session"], bot_username, text),
    )


async def card_command(
    message: Message,
    state: FSMContext,
    profiles: ProfileStore,
    bot_username: str = "",
) -> None:
    if data := await ensure_profile(message, state, profiles):
        await send_card(message, data, bot_username)


async def action_callback(
    callback: CallbackQuery,
    callback_data: ActionCallback,
    state: FSMContext,
    profiles: ProfileStore,
    bot_username: str = "",
) -> None:
    data = await state.get_data()
    if data.get("session") != callback_data.session:
        await callback.answer(
            "Эти кнопки устарели. Открой /menu.", show_alert=True
        )
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Открой личный чат с ботом.")
        return
    await callback.answer()
    message, action = callback.message, callback_data.action
    if action == "menu":
        await message.answer(
            profile_text(data), reply_markup=menu_keyboard(data["session"])
        )
    elif action == "change":
        await state.clear()
        await message.answer(
            "Введи новую дату в формате ДД.ММ. Например: 09.03."
        )
    elif action == "ai":
        await message.answer(
            "💬 <b>Что хочется узнать?</b>\n\n"
            "Попробуй: «музыканты моего знака», «Влад А4», "
            "«кто родился 09.03» или «актёры в июне».\n\n"
            "Просто отправь вопрос сообщением.",
            reply_markup=back_keyboard(data["session"]),
        )
    elif action == "quiz":
        await send_quiz(message, state, data)
    elif action == "card":
        await send_card(message, data, bot_username)
    elif action == "stats":
        score = profiles.get(callback.from_user.id)
        played = score["played"] if score else 0
        correct = score["correct"] if score else 0
        percent = round(100 * correct / played) if played else 0
        await message.answer(
            f"📊 <b>Твоя статистика</b>\n\nВопросов: {played}\n"
            f"Верных ответов: {correct}\nТочность: {percent}%\n\n"
            "Ещё один раунд?",
            reply_markup=quiz_result_keyboard(data["session"]),
        )
    elif action == "today":
        current = today()
        people = search_catalog(day=current.day, month=current.month)
        await state.update_data(today_date=current.isoformat())
        page = people[:PAGE_SIZE]
        if not page:
            await message.answer(
                "🎂 Сегодня в нашем каталоге именинников нет. "
                "Зато можно посмотреть свой знак или сыграть в викторину.",
                reply_markup=back_keyboard(data["session"]),
            )
            return
        await message.answer(
            f"🎂 <b>Сегодня, {current:%d.%m}, празднуют</b>\n\n"
            f"{format_celebrities(page)}",
            reply_markup=pagination_keyboard(
                "today", data["session"], len(page)
            ),
        )
        await state.update_data(today_offset=len(page))


async def outdated_callback(callback: CallbackQuery) -> None:
    await callback.answer("Кнопка больше не поддерживается. Открой /menu.")


def create_router() -> Router:
    router = Router()
    router.message.filter(F.chat.type == "private")
    router.callback_query.filter(F.message.chat.type == "private")
    router.message.register(start, CommandStart())
    for command, handler in [
        ("help", help_command),
        ("menu", menu),
        ("search", search_command),
        ("ai", ai_command),
        ("quiz", quiz_command),
        ("card", card_command),
        ("forget", forget),
    ]:
        router.message.register(handler, Command(command))
    router.message.register(receive_message)
    router.callback_query.register(
        celebrities_by_day, CelebrityCallback.filter(F.category == "day")
    )
    router.callback_query.register(
        celebrities_by_sign, CelebrityCallback.filter(F.category == "sign")
    )
    router.callback_query.register(send_page, CelebrityCallback.filter())
    router.callback_query.register(action_callback, ActionCallback.filter())
    router.callback_query.register(answer_quiz, QuizCallback.filter())
    router.callback_query.register(outdated_callback)
    return router
