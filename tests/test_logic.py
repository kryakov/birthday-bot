import unittest
from datetime import date, timedelta

from celebrities import (
    CELEBRITIES,
    get_celebrities_by_day,
    get_celebrities_by_sign,
)
from zodiac import ZODIAC_DESCRIPTIONS, get_zodiac_sign, validate_birth_date


class DateTests(unittest.TestCase):
    def test_valid_dates(self):
        for text, expected in [
            ("01.01", (1, 1)),
            ("29.02", (29, 2)),
            ("31.12", (31, 12)),
            (" 26.06 ", (26, 6)),
        ]:
            with self.subTest(text=text):
                self.assertEqual(validate_birth_date(text), expected)

    def test_invalid_dates(self):
        for text in [
            None,
            "",
            "hello",
            "1.03",
            "01.3",
            "01/03",
            "01.03.2000",
            "00.01",
            "01.00",
            "31.04",
            "30.02",
            "32.01",
            "01.13",
            "０１.０３",
            "01. 03",
            "-1.03",
            "01.03\n02.03",
        ]:
            with self.subTest(text=text):
                self.assertIsNone(validate_birth_date(text))

    def test_zodiac_boundaries(self):
        cases = [
            (19, 1, "Козерог"),
            (20, 1, "Водолей"),
            (18, 2, "Водолей"),
            (19, 2, "Рыбы"),
            (20, 3, "Рыбы"),
            (21, 3, "Овен"),
            (19, 4, "Овен"),
            (20, 4, "Телец"),
            (20, 5, "Телец"),
            (21, 5, "Близнецы"),
            (20, 6, "Близнецы"),
            (21, 6, "Рак"),
            (22, 7, "Рак"),
            (23, 7, "Лев"),
            (22, 8, "Лев"),
            (23, 8, "Дева"),
            (22, 9, "Дева"),
            (23, 9, "Весы"),
            (22, 10, "Весы"),
            (23, 10, "Скорпион"),
            (21, 11, "Скорпион"),
            (22, 11, "Стрелец"),
            (21, 12, "Стрелец"),
            (22, 12, "Козерог"),
            (31, 12, "Козерог"),
            (1, 1, "Козерог"),
            (29, 2, "Рыбы"),
        ]
        for day, month, expected in cases:
            with self.subTest(day=day, month=month):
                self.assertEqual(get_zodiac_sign(day, month), expected)

    def test_every_calendar_day_has_a_description(self):
        day = date(2000, 1, 1)
        for offset in range(366):
            birthday = day + timedelta(days=offset)
            sign = get_zodiac_sign(birthday.day, birthday.month)
            self.assertTrue(ZODIAC_DESCRIPTIONS[sign])


class CelebrityTests(unittest.TestCase):
    def test_database_dates_signs_and_unique_people(self):
        names = set()
        for person in CELEBRITIES:
            name = person["first_name"], person["last_name"]
            with self.subTest(name=name):
                self.assertNotIn(name, names)
                names.add(name)
                self.assertEqual(
                    get_zodiac_sign(person["day"], person["month"]),
                    person["zodiac"],
                )
                self.assertTrue(person["description"])

    def test_day_pages_filter_both_parts_and_do_not_repeat(self):
        first = get_celebrities_by_day(26, 6)
        second = get_celebrities_by_day(26, 6, 3)
        self.assertEqual(len(first), 3)
        self.assertGreaterEqual(len(second), 1)
        self.assertTrue(all(p["day"] == 26 and p["month"] == 6 for p in first))
        self.assertTrue(all(person not in first for person in second))
        self.assertEqual(get_celebrities_by_day(26, 6, 999), [])
        self.assertTrue(
            all(p["month"] == 3 for p in get_celebrities_by_day(26, 3))
        )
        self.assertEqual(
            get_celebrities_by_day(25, 6)[0]["nickname"], "Егор Крид"
        )

    def test_sign_includes_different_dates_without_repeats(self):
        people = []
        while page := get_celebrities_by_sign("Рак", len(people)):
            self.assertLessEqual(len(page), 3)
            self.assertTrue(all(person not in people for person in page))
            people.extend(page)
        self.assertGreaterEqual(len(people), 9)
        self.assertTrue(all(p["zodiac"] == "Рак" for p in people))
        self.assertTrue({25, 26, 27}.issubset({p["day"] for p in people}))

    def test_empty_results(self):
        self.assertEqual(get_celebrities_by_day(31, 2), [])
        self.assertEqual(get_celebrities_by_sign("Нет такого знака"), [])

    def test_negative_offset_is_rejected(self):
        with self.assertRaises(ValueError):
            get_celebrities_by_day(26, 6, -1)
        with self.assertRaises(ValueError):
            get_celebrities_by_sign("Рак", -1)
