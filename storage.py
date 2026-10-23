import sqlite3
from pathlib import Path


class ProfileStore:
    def __init__(self, path: str | Path = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS profiles ("
            "user_id INTEGER PRIMARY KEY, day INTEGER NOT NULL, "
            "month INTEGER NOT NULL, correct INTEGER NOT NULL DEFAULT 0, "
            "played INTEGER NOT NULL DEFAULT 0)"
        )
        self.connection.commit()

    def get(self, user_id: int) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None

    def save_birthday(self, user_id: int, day: int, month: int) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO profiles (user_id, day, month) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "day = excluded.day, month = excluded.month",
                (user_id, day, month),
            )

    def record_answer(self, user_id: int, correct: bool) -> dict:
        with self.connection:
            self.connection.execute(
                "UPDATE profiles SET played = played + 1, "
                "correct = correct + ? WHERE user_id = ?",
                (int(correct), user_id),
            )
        return self.get(user_id) or {"played": 0, "correct": 0}

    def forget(self, user_id: int) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM profiles WHERE user_id = ?", (user_id,)
            )

    def close(self) -> None:
        self.connection.close()
