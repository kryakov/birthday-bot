import asyncio
import os
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InputProfilePhotoStatic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


async def main():
    load_dotenv(ROOT / ".env")
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "put_your_token_here":
        raise SystemExit("Сначала укажи BOT_TOKEN в .env.")
    async with Bot(token=token) as bot:
        me = await bot.get_me()
        await bot.set_my_description(
            "У каждого дня — свои звёзды. Найди знаменитостей с твоей датой "
            "рождения, спроси локальный AI, сыграй в «Угадай знак» "
            "и поделись своей карточкой с друзьями. Начни с /start."
        )
        await bot.set_my_short_description(
            "Знаменитости твоего дня рождения · AI-поиск · викторина"
        )
        await bot.set_my_profile_photo(
            InputProfilePhotoStatic(
                photo=FSInputFile(ROOT / "assets/avatar.jpg")
            )
        )
        print(f"Оформление обновлено: @{me.username}")


if __name__ == "__main__":
    asyncio.run(main())
