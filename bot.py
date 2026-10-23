import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import BotCommand, LinkPreviewOptions
from aiogram.utils.token import TokenValidationError
from dotenv import load_dotenv

from assistant import LlamaAssistant
from handlers import create_router
from storage import ProfileStore

ROOT = Path(__file__).parent


def create_dispatcher(
    profiles: ProfileStore | None = None,
    assistant: LlamaAssistant | None = None,
    bot_username: str = "",
) -> Dispatcher:
    dispatcher = Dispatcher(
        storage=MemoryStorage(),
        events_isolation=SimpleEventIsolation(),
        profiles=profiles or ProfileStore(),
        assistant=assistant or LlamaAssistant(),
        bot_username=bot_username,
    )
    dispatcher.include_router(create_router())
    return dispatcher


async def main() -> None:
    load_dotenv(ROOT / ".env")
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "put_your_token_here":
        raise SystemExit("Укажи BOT_TOKEN в файле .env рядом с bot.py.")
    try:
        bot = Bot(
            token=token,
            default=DefaultBotProperties(
                parse_mode=ParseMode.HTML,
                link_preview=LinkPreviewOptions(is_disabled=True),
            ),
        )
    except TokenValidationError:
        raise SystemExit(
            "Неверный формат BOT_TOKEN. Проверь токен из BotFather."
        )
    profiles = ProfileStore(ROOT / "data/profiles.sqlite")
    assistant = LlamaAssistant(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        model=os.getenv("OLLAMA_MODEL", "llama3.1:latest"),
    )
    try:
        async with bot:
            try:
                me = await bot.get_me()
                await bot.set_my_commands(
                    [
                        BotCommand(
                            command="start",
                            description="Знакомство и мой профиль",
                        ),
                        BotCommand(command="menu", description="Главное меню"),
                        BotCommand(
                            command="search", description="Найти знаменитость"
                        ),
                        BotCommand(command="quiz", description="Угадай знак"),
                        BotCommand(command="card", description="Моя карточка"),
                        BotCommand(command="ai", description="Проверить AI"),
                        BotCommand(
                            command="help", description="Как всё устроено"
                        ),
                        BotCommand(
                            command="forget", description="Удалить мои данные"
                        ),
                    ]
                )
            except TelegramUnauthorizedError:
                raise SystemExit(
                    "Telegram отклонил BOT_TOKEN. Проверь токен из BotFather."
                )
            logging.info("Бот запущен; модель Ollama: %s", assistant.model)
            await create_dispatcher(
                profiles, assistant, me.username or ""
            ).start_polling(bot, close_bot_session=False)
    finally:
        profiles.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
