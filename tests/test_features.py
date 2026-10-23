import json
import tempfile
import unittest
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from assistant import (
    AIBusy,
    AIUnavailable,
    LlamaAssistant,
    execute_plan,
    fallback_plan,
)
from celebrities import CELEBRITIES, format_celebrities, search_catalog
from experience import days_until_birthday, make_quiz, share_text
from storage import ProfileStore
from zodiac import ZODIAC_DESCRIPTIONS


class CatalogTests(unittest.TestCase):
    def test_every_calendar_day_has_at_least_four_people(self):
        counts = Counter((p["day"], p["month"]) for p in CELEBRITIES)
        for offset in range(366):
            birthday = date(2000, 1, 1) + timedelta(days=offset)
            with self.subTest(date=birthday.strftime("%d.%m")):
                self.assertGreaterEqual(
                    counts[birthday.day, birthday.month], 4
                )

    def test_all_signs_and_sources(self):
        self.assertGreaterEqual(len(CELEBRITIES), 150)
        self.assertEqual(
            {p["zodiac"] for p in CELEBRITIES}, set(ZODIAC_DESCRIPTIONS)
        )
        self.assertEqual(len({p["id"] for p in CELEBRITIES}), len(CELEBRITIES))
        for person in CELEBRITIES:
            self.assertTrue(person["source"].startswith("https://"))

    def test_alias_and_combined_filters(self):
        self.assertTrue(search_catalog("MrBeast"))
        self.assertTrue(search_catalog("Инстасамка"))
        self.assertTrue(search_catalog("Билли Айлиш"))
        result = search_catalog(sign="Рак", category="music")
        self.assertTrue(result)
        self.assertTrue(
            all(
                p["zodiac"] == "Рак" and p["category"] == "music"
                for p in result
            )
        )

    def test_html_is_escaped(self):
        person = dict(
            CELEBRITIES[0], first_name="<script>", description="A & B"
        )
        text = format_celebrities([person])
        self.assertIn("&lt;script&gt;", text)
        self.assertIn("A &amp; B", text)


class ExperienceTests(unittest.TestCase):
    def test_countdown_and_leap_day(self):
        self.assertEqual(days_until_birthday(26, 6, date(2026, 6, 26)), 0)
        self.assertEqual(days_until_birthday(1, 1, date(2026, 12, 31)), 1)
        self.assertEqual(days_until_birthday(29, 2, date(2027, 3, 1)), 365)

    def test_quiz_has_unique_choices_and_no_recent_person(self):
        first = make_quiz()
        second = make_quiz([first["person_id"]])
        self.assertNotEqual(first["person_id"], second["person_id"])
        self.assertEqual(len(set(first["options"])), 4)
        person = next(p for p in CELEBRITIES if p["id"] == first["person_id"])
        self.assertEqual(first["options"][first["correct"]], person["zodiac"])

    def test_card_does_not_claim_same_day_if_no_matches(self):
        with patch(
            "experience.search_catalog",
            side_effect=[[], search_catalog(sign="Рыбы")],
        ):
            text = share_text({"day": 29, "month": 2, "sign": "Рыбы"})
        self.assertIn("Мой знак делят", text)
        self.assertNotIn("в один день", text)


class StorageTests(unittest.TestCase):
    def test_persistence_updates_and_forget(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profiles.sqlite"
            store = ProfileStore(path)
            store.save_birthday(1, 26, 6)
            store.record_answer(1, True)
            store.save_birthday(1, 9, 3)
            store.close()
            store = ProfileStore(path)
            self.assertEqual(store.get(1)["month"], 3)
            self.assertEqual(store.get(1)["correct"], 1)
            self.assertIsNone(store.get(2))
            store.forget(1)
            self.assertIsNone(store.get(1))
            store.close()


class AssistantTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_plan_searches_real_catalog(self):
        ai = LlamaAssistant()
        ai._chat = AsyncMock(
            return_value=json.dumps({"personal": "sign", "category": "music"})
        )
        answer = await ai.ask(
            "музыканты моего знака", {"day": 26, "month": 6, "sign": "Рак"}
        )
        self.assertTrue(answer.used_ai)
        self.assertTrue(
            all(
                p["zodiac"] == "Рак" and p["category"] == "music"
                for p in answer.people
            )
        )
        self.assertGreater(answer.total, 3)

    async def test_explicit_month_overrides_model_mistake(self):
        ai = LlamaAssistant()
        ai._chat = AsyncMock(
            return_value=json.dumps({"month": 7, "category": "screen"})
        )
        answer = await ai.ask("актёры, родившиеся в июне", {})
        self.assertTrue(answer.people)
        self.assertTrue(all(p["month"] == 6 for p in answer.people))
        self.assertTrue(all(p["category"] == "screen" for p in answer.people))

    async def test_offline_fallback(self):
        ai = LlamaAssistant()
        ai._chat = AsyncMock(side_effect=AIUnavailable())
        answer = await ai.ask("Билли Айлиш", {})
        self.assertFalse(answer.used_ai)
        self.assertEqual(answer.people[0]["day"], 18)
        self.assertEqual(answer.people[0]["month"], 12)

    async def test_invalid_model_json_falls_back(self):
        ai = LlamaAssistant()
        ai._chat = AsyncMock(return_value="not json")
        answer = await ai.ask("кто родился 09.03", {})
        self.assertFalse(answer.used_ai)
        self.assertTrue(
            all(p["day"] == 9 and p["month"] == 3 for p in answer.people)
        )

    async def test_missing_person_is_not_invented(self):
        ai = LlamaAssistant()
        ai._chat = AsyncMock(
            return_value=json.dumps({"query": "Несуществующий Человек"})
        )
        answer = await ai.ask("Несуществующий Человек", {})
        self.assertEqual(answer.people, [])

    async def test_busy_model_has_no_unbounded_queue(self):
        ai = LlamaAssistant()
        await ai.lock.acquire()
        try:
            with self.assertRaises(AIBusy):
                await ai.ask("Привет", {})
        finally:
            ai.lock.release()

    async def test_timeout_becomes_unavailable(self):
        ai = LlamaAssistant(base_url="http://127.0.0.1:1", timeout=0.1)
        with self.assertRaises(AIUnavailable):
            await ai._chat([])

    def test_offline_month_and_category(self):
        plan = fallback_plan("актёры в июне", {})
        self.assertEqual((plan.month, plan.category), (6, "screen"))
        self.assertTrue(all(p["month"] == 6 for p in execute_plan(plan, {})))
