"""Persistent domain state for the Telegram/MQTT bridge."""

import json
import re
import sqlite3
from pathlib import Path

BOT_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
CHAT_ID = re.compile(r"^-?[0-9]{1,20}$")


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(str(Path(path)))
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS bots (
            id TEXT PRIMARY KEY, token TEXT NOT NULL, offset INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS chats (
            bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            chat_id TEXT NOT NULL, allowed INTEGER NOT NULL DEFAULT 0,
            label TEXT NOT NULL DEFAULT '', PRIMARY KEY(bot_id, chat_id)
        );
        CREATE TABLE IF NOT EXISTS outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
            bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            request_id TEXT NOT NULL, chat_id TEXT NOT NULL, text TEXT NOT NULL,
            state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(bot_id, request_id)
        );
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def add_bot(self, bot_id, token):
        if not BOT_ID.fullmatch(bot_id) or not token:
            raise ValueError("invalid bot")
        with self.db:
            self.db.execute("INSERT INTO bots(id, token) VALUES (?, ?)", (bot_id, token))

    def allow(self, bot_id, chat_id, allowed=True):
        if not CHAT_ID.fullmatch(chat_id):
            raise ValueError("invalid chat ID")
        with self.db:
            self.db.execute("""INSERT INTO chats(bot_id,chat_id,allowed) VALUES(?,?,?)
                ON CONFLICT(bot_id,chat_id) DO UPDATE SET allowed=excluded.allowed""",
                (bot_id, chat_id, int(allowed)))

    def _allowed(self, bot_id, chat_id):
        row = self.db.execute("SELECT allowed FROM chats WHERE bot_id=? AND chat_id=?",
                              (bot_id, chat_id)).fetchone()
        return bool(row and row[0])

    def _publish(self, bot_id, kind, payload):
        self.db.execute("INSERT INTO outbox(topic,payload) VALUES(?,?)", (
            f"telegram2mqtt/v1/{bot_id}/{kind}", json.dumps(payload, ensure_ascii=False)))

    def ingest_update(self, bot_id, update_id, chat_id, text, timestamp, label=""):
        """Persist an update and its next offset atomically; never publish unknown text."""
        if not isinstance(update_id, int) or update_id < 0 or not CHAT_ID.fullmatch(chat_id):
            raise ValueError("invalid update")
        with self.db:
            row = self.db.execute("SELECT offset FROM bots WHERE id=?", (bot_id,)).fetchone()
            if row is None:
                raise KeyError(bot_id)
            if update_id < row[0]:
                return
            if self._allowed(bot_id, chat_id):
                if isinstance(text, str):
                    self._publish(bot_id, "event/message", {
                        "event_id": f"{bot_id}:{update_id}", "chat_id": chat_id,
                        "text": text, "timestamp": timestamp,
                    })
            else:
                self.db.execute("""INSERT INTO chats(bot_id,chat_id,label) VALUES(?,?,?)
                    ON CONFLICT(bot_id,chat_id) DO UPDATE SET label=excluded.label""",
                    (bot_id, chat_id, label[:200]))
            self.db.execute("UPDATE bots SET offset=? WHERE id=?", (update_id + 1, bot_id))

    def submit(self, bot_id, request_id, chat_id, text):
        """Persist an idempotent outgoing job and its correlated acceptance/result."""
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError("invalid request ID")
        with self.db:
            existing = self.db.execute("SELECT chat_id,text,state FROM jobs WHERE bot_id=? AND request_id=?",
                                       (bot_id, request_id)).fetchone()
            if existing:
                if existing[:2] != (chat_id, text):
                    self._publish(bot_id, "event/result", {"request_id": request_id,
                                  "status": "rejected", "error_code": "request_id_conflict"})
                    return "conflict"
                return existing[2]
            valid = (isinstance(chat_id, str) and CHAT_ID.fullmatch(chat_id) and
                     isinstance(text, str) and 1 <= len(text) <= 4096)
            code = None if valid else "invalid_request"
            if not code and not self._allowed(bot_id, chat_id):
                code = "chat_not_allowed"
            state = "rejected" if code else "pending"
            self.db.execute("INSERT INTO jobs(bot_id,request_id,chat_id,text,state) VALUES(?,?,?,?,?)",
                            (bot_id, request_id, str(chat_id), text if isinstance(text, str) else "", state))
            result = {"request_id": request_id, "status": state}
            if code:
                result["error_code"] = code
            self._publish(bot_id, "event/result", result)
            return state

    def claim(self, bot_id):
        """Claim one job, checking current authorization immediately before sending."""
        with self.db:
            row = self.db.execute("SELECT request_id,chat_id,text FROM jobs WHERE bot_id=? AND state='pending' ORDER BY rowid LIMIT 1", (bot_id,)).fetchone()
            if not row:
                return None
            request_id, chat_id, text = row
            if not self._allowed(bot_id, chat_id):
                self.db.execute("UPDATE jobs SET state='rejected' WHERE bot_id=? AND request_id=?", (bot_id, request_id))
                self._publish(bot_id, "event/result", {"request_id": request_id, "status": "rejected", "error_code": "chat_not_allowed"})
                return None
            self.db.execute("UPDATE jobs SET state='sending',attempts=attempts+1 WHERE bot_id=? AND request_id=?", (bot_id, request_id))
            return row

    def finish(self, bot_id, request_id, message_id=None, retry=False):
        with self.db:
            row = self.db.execute("SELECT state FROM jobs WHERE bot_id=? AND request_id=?", (bot_id, request_id)).fetchone()
            if not row or row[0] != "sending":
                raise ValueError("job is not sending")
            state = "pending" if retry else "sent"
            self.db.execute("UPDATE jobs SET state=? WHERE bot_id=? AND request_id=?", (state, bot_id, request_id))
            result = {"request_id": request_id, "status": state}
            if message_id is not None:
                result["message_id"] = str(message_id)
            self._publish(bot_id, "event/result", result)

    def recover(self):
        """A send interrupted by shutdown is ambiguous; retry can create duplicates."""
        with self.db:
            self.db.execute("UPDATE jobs SET state='pending' WHERE state='sending'")

    def next_publication(self):
        return self.db.execute("SELECT id,topic,payload FROM outbox ORDER BY id LIMIT 1").fetchone()

    def publication_confirmed(self, item_id):
        with self.db:
            self.db.execute("DELETE FROM outbox WHERE id=?", (item_id,))
