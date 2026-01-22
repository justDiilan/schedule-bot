import sqlite3
from dataclasses import dataclass
from typing import Optional, List, Tuple

@dataclass
class Subscription:
    user_id: int
    provider: str
    region_code: str
    group_num: str
    subgroup_num: str
    last_hash: str

class DB:
    def __init__(self, path: str = "bot.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            provider TEXT NOT NULL,
            region_code TEXT NOT NULL,
            group_num TEXT NOT NULL,
            subgroup_num TEXT NOT NULL,
            last_hash TEXT NOT NULL DEFAULT ''
        )
        """)
        # Safe migration: add username column if not exists
        cur = self.conn.execute("PRAGMA table_info(subscriptions)")
        columns = [row[1] for row in cur.fetchall()]
        if "username" not in columns:
            self.conn.execute("ALTER TABLE subscriptions ADD COLUMN username TEXT")
            
        self.conn.commit()

    def upsert_subscription(self, user_id: int, provider: str, region_code: str, group_num: str, subgroup_num: str, username: str = None):
        self.conn.execute("""
        INSERT INTO subscriptions(user_id, provider, region_code, group_num, subgroup_num, last_hash, username)
        VALUES(?,?,?,?,?,COALESCE((SELECT last_hash FROM subscriptions WHERE user_id=?), ''), ?)
        ON CONFLICT(user_id) DO UPDATE SET
          provider=excluded.provider,
          region_code=excluded.region_code,
          group_num=excluded.group_num,
          subgroup_num=excluded.subgroup_num,
          username=excluded.username
        """, (user_id, provider, region_code, group_num, subgroup_num, user_id, username))
        self.conn.commit()

    def delete_subscription(self, user_id: int):
        self.conn.execute("DELETE FROM subscriptions WHERE user_id=?", (user_id,))
        self.conn.commit()

    def set_last_hash(self, user_id: int, last_hash: str):
        self.conn.execute("UPDATE subscriptions SET last_hash=? WHERE user_id=?", (last_hash, user_id))
        self.conn.commit()

    def get_subscription(self, user_id: int) -> Optional[Subscription]:
        cur = self.conn.execute("""
        SELECT user_id, provider, region_code, group_num, subgroup_num, last_hash
        FROM subscriptions WHERE user_id=?
        """, (user_id,))
        row = cur.fetchone()
        return Subscription(*row) if row else None

    def list_subscriptions(self) -> List[Subscription]:
        cur = self.conn.execute("""
        SELECT user_id, provider, region_code, group_num, subgroup_num, last_hash
        FROM subscriptions
        """)
        return [Subscription(*r) for r in cur.fetchall()]

    def get_stats(self) -> List[Tuple[int, Optional[str]]]:
        """Returns list of (user_id, username)"""
        cur = self.conn.execute("SELECT user_id, username FROM subscriptions")
        return cur.fetchall()

    def get_all_user_ids(self) -> List[int]:
        cur = self.conn.execute("SELECT user_id FROM subscriptions")
        return [r[0] for r in cur.fetchall()]
