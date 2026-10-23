import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import (
    AnswerCallbackQuery,
    SendChatAction,
    SendMessage,
    SendPhoto,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    Message,
    MessageEntity,
    Update,
    User,
)

from assistant import LlamaAssistant, SearchReply
from bot import create_dispatcher
from celebrities import search_catalog
from handlers import EMPTY_MESSAGE
from keyboards import CelebrityCallback
from storage import ProfileStore


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = Bot("123456:local_test_token")
        self.bot.session.make_request = AsyncMock(side_effect=self.respond)
        self.profiles = ProfileStore()
        self.assistant = AsyncMock(spec=LlamaAssistant)
        self.dispatcher = create_dispatcher(
            self.profiles, self.assistant, "BirthdayDemoBot"
        )
        self.messages = []
        self.answers = []
        self.update_id = 0
        self.fail_next_send = False

    async def asyncTearDown(self):
        await self.dispatcher.fsm.close()
        self.profiles.close()
        await self.bot.session.close()

    async def respond(self, bot, method, **kwargs):
        if isinstance(method, (SendMessage, SendPhoto)):
            if self.fail_next_send:
                self.fail_next_send = False
                raise TelegramNetworkError(method=method, message="Test error")
            text = (
                method.text
                if isinstance(method, SendMessage)
                else method.caption
            )
            self.assertLessEqual(
                len(text), 4096 if isinstance(method, SendMessage) else 1024
            )
            message = Message(
                message_id=len(self.messages) + 1,
                date=datetime.now(timezone.utc),
                chat=Chat(id=method.chat_id, type="private"),
                from_user=User(id=123456, is_bot=True, first_name="Bot"),
                text=text,
                reply_markup=method.reply_markup,
            )
            self.messages.append(message)
            return message
        if isinstance(method, AnswerCallbackQuery):
            self.answers.append(method)
            return True
        if isinstance(method, SendChatAction):
            return True
        raise AssertionError(f"Unexpected API call: {type(method).__name__}")

    async def send(self, text, user_id=1):
        self.update_id += 1
        entities = None
        if text and text.startswith("/"):
            entities = [
                MessageEntity(
                    type="bot_command", offset=0, length=len(text.split()[0])
                )
            ]
        message = Message(
            message_id=self.update_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=user_id, type="private"),
            from_user=User(id=user_id, is_bot=False, first_name="Тест"),
            text=text,
            entities=entities,
        )
        await self.dispatcher.feed_update(
            self.bot, Update(update_id=self.update_id, message=message)
        )
        return self.messages[-1]

    async def click(self, message, row=0, column=0, user_id=1):
        self.update_id += 1
        callback = CallbackQuery(
            id=str(self.update_id),
            from_user=User(id=user_id, is_bot=False, first_name="Тест"),
            chat_instance="test",
            message=message,
            data=message.reply_markup.inline_keyboard[row][
                column
            ].callback_data,
        )
        await self.dispatcher.feed_update(
            self.bot, Update(update_id=self.update_id, callback_query=callback)
        )
        return self.messages[-1]

    async def user_data(self, user_id=1):
        context = self.dispatcher.fsm.get_context(
            bot=self.bot, chat_id=user_id, user_id=user_id
        )
        return await context.get_data()

    async def test_start_invalid_input_and_birthday_menu(self):
        self.assertIn("ДД.ММ", (await self.send("/start")).text)
        for text in ["31.04", "1.3", None]:
            self.assertIn("Не получилось", (await self.send(text)).text)
            self.assertIsNone(self.profiles.get(1))
        menu = await self.send("26.06")
        self.assertIn("Рак", menu.text)
        self.assertEqual(self.profiles.get(1)["day"], 26)
        self.assertEqual(
            menu.reply_markup.inline_keyboard[0][0].text,
            "Знаменитости в этот день",
        )
        self.assertEqual(
            menu.reply_markup.inline_keyboard[1][0].text,
            "Знаменитости этого знака",
        )

    async def test_day_pages_exhaust_without_duplicates(self):
        menu = await self.send("26.06")
        page = await self.click(menu)
        texts = []
        total = len(search_catalog(day=26, month=6))
        for _ in range((total + 2) // 3):
            texts.append(page.text)
            page = await self.click(page)
        self.assertEqual(page.text, EMPTY_MESSAGE)
        self.assertEqual((await self.user_data())["day_offset"], total)
        self.assertEqual("\n".join(texts).count("Ариана Гранде"), 1)
        self.assertEqual("\n".join(texts).count("Обри Плаза"), 1)

    async def test_switching_categories_keeps_progress(self):
        menu = await self.send("26.06")
        day_page = await self.click(menu)
        sign_page = await self.click(menu, row=1)
        self.assertIn("Егор Крид", sign_page.text)
        await self.click(day_page)
        data = await self.user_data()
        self.assertEqual(data["sign_offset"], 3)
        self.assertGreater(data["day_offset"], 3)
        self.assertIn("Бенсон Бун", (await self.click(sign_page)).text)

    async def test_reusing_menu_does_not_restart(self):
        menu = await self.send("26.06")
        await self.click(menu)
        page = await self.click(menu)
        self.assertIn("Обри Плаза", page.text)
        self.assertNotIn("Ариана Гранде", page.text)

    async def test_simultaneous_more_clicks_send_one_page(self):
        menu = await self.send("26.06")
        first = await self.click(menu)
        before = len(self.messages)
        await asyncio.gather(self.click(first), self.click(first))
        self.assertEqual(len(self.messages), before + 1)
        self.assertIn("уже показана", self.answers[-1].text)

    async def test_users_have_separate_progress(self):
        first = await self.send("26.06", user_id=1)
        second = await self.send("09.03", user_id=2)
        await asyncio.gather(
            self.click(first, user_id=1), self.click(second, user_id=2)
        )
        self.assertEqual((await self.user_data(1))["day_offset"], 3)
        self.assertEqual((await self.user_data(2))["day_offset"], 3)
        self.assertEqual(self.profiles.get(2)["month"], 3)

    async def test_new_date_rejects_old_buttons(self):
        menu = await self.send("26.06")
        await self.send("11.05")
        before = len(self.messages)
        await self.click(menu)
        self.assertEqual(len(self.messages), before)
        self.assertTrue(self.answers[-1].show_alert)

    async def test_restart_restores_profile_and_rejects_old_menu(self):
        menu = await self.send("26.06")
        await self.dispatcher.fsm.close()
        self.dispatcher = create_dispatcher(self.profiles, self.assistant)
        response = await self.send("/start")
        self.assertIn("С возвращением", response.text)
        self.assertEqual((await self.user_data())["day_offset"], 0)
        before = len(self.messages)
        await self.click(menu)
        self.assertEqual(len(self.messages), before)

    async def test_forget_deletes_birthday_and_score(self):
        await self.send("26.06")
        self.profiles.record_answer(1, True)
        await self.send("/forget")
        self.assertIsNone(self.profiles.get(1))
        self.assertEqual(await self.user_data(), {})

    async def test_failed_send_does_not_advance_page(self):
        menu = await self.send("26.06")
        self.fail_next_send = True
        with self.assertRaises(TelegramNetworkError):
            await self.click(menu)
        self.assertEqual((await self.user_data())["day_offset"], 0)
        self.assertIn("Ариана Гранде", (await self.click(menu)).text)

    async def test_invalid_date_and_help_preserve_profile(self):
        await self.send("26.06")
        before = await self.user_data()
        await self.send("31.02")
        await self.send("/help")
        self.assertEqual(await self.user_data(), before)
        self.assistant.ask.assert_not_called()

    async def test_empty_day_can_show_sign(self):
        menu = await self.send("29.02")
        with patch("handlers.search_catalog", return_value=[]):
            empty = await self.click(menu)
        self.assertEqual(empty.text, EMPTY_MESSAGE)
        self.assertIn("Джастин Бибер", (await self.click(empty, row=1)).text)

    async def test_leap_day_has_two_pages(self):
        menu = await self.send("29.02")
        first = await self.click(menu)
        second = await self.click(first)
        self.assertIn("29.02", first.text)
        self.assertIn("29.02", second.text)
        self.assertNotEqual(first.text, second.text)
        self.assertEqual((await self.click(second)).text, EMPTY_MESSAGE)

    async def test_quiz_scores_exactly_once(self):
        await self.send("26.06")
        question = await self.send("/quiz")
        quiz = (await self.user_data())["quiz"]
        correct = quiz["correct"]
        answer = await self.click(
            question, row=correct // 2, column=correct % 2
        )
        self.assertIn("Верно", answer.text)
        await self.click(question, row=correct // 2, column=correct % 2)
        profile = self.profiles.get(1)
        self.assertEqual((profile["correct"], profile["played"]), (1, 1))
        self.assertIsNone(self.profiles.get(123456))

    async def test_wrong_quiz_answer_is_recorded(self):
        await self.send("26.06")
        question = await self.send("/quiz")
        quiz = (await self.user_data())["quiz"]
        wrong = (quiz["correct"] + 1) % 4
        await self.click(question, row=wrong // 2, column=wrong % 2)
        self.assertEqual(self.profiles.get(1)["played"], 1)
        self.assertEqual(self.profiles.get(1)["correct"], 0)

    async def test_share_card_contains_correct_bot_link(self):
        await self.send("26.06")
        card = await self.send("/card")
        self.assertIn("26.06", card.text)
        self.assertIn("Ариана Гранде", card.text)
        self.assertIn(
            "BirthdayDemoBot", card.reply_markup.inline_keyboard[0][0].url
        )

    async def test_ai_search_has_more_than_one_page(self):
        await self.send("26.06")
        people = search_catalog(sign="Рак")
        self.assistant.ask.return_value = SearchReply(
            "Вот подборка.", people, True, len(people)
        )
        page = await self.send("музыканты моего знака")
        self.assertIn("Егор Крид", page.text)
        more = await self.click(page)
        self.assertIn("Бенсон Бун", more.text)
        self.assertEqual((await self.user_data())["day_offset"], 0)

    async def test_new_search_invalidates_previous_search_buttons(self):
        await self.send("26.06")
        people = search_catalog(sign="Рак")
        self.assistant.ask.return_value = SearchReply(
            "Подборка.", people, False, len(people)
        )
        old = await self.send("рак")
        await self.send("рыбы")
        before = len(self.messages)
        await self.click(old)
        self.assertEqual(len(self.messages), before)
        self.assertIn("устарели", self.answers[-1].text)

    async def test_callback_data_is_short_enough(self):
        menu = await self.send("26.06")
        page = await self.click(menu)
        for message in (menu, page):
            for row in message.reply_markup.inline_keyboard:
                for button in row:
                    self.assertLessEqual(
                        len(button.callback_data.encode()), 64
                    )
        value = page.reply_markup.inline_keyboard[0][0].callback_data
        self.assertEqual(CelebrityCallback.unpack(value).pack(), value)
