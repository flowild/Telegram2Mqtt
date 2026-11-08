import json
import tempfile
import unittest
from pathlib import Path
from telegram2mqtt.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.db"
        self.store = Store(self.path)
        self.store.add_bot("one", "token")
        self.store.add_bot("two", "other")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_unknown_text_never_enters_outbox_and_is_bot_scoped(self):
        self.store.allow("one", "123")
        self.store.ingest_update("two", 1, "123", "private", 1, "contact")
        self.assertIsNone(self.store.next_publication())
        self.assertEqual(self.store.db.execute("SELECT allowed FROM chats WHERE bot_id='two'").fetchone()[0], 0)
        self.store.ingest_update("one", 2, "123", "hello", 2)
        self.assertEqual(json.loads(self.store.next_publication()[2])["text"], "hello")
        self.store.ingest_update("one", 2, "123", "hello", 2)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 1)

    def test_idempotency_revocation_and_recovery(self):
        self.store.allow("one", "-42")
        self.assertEqual(self.store.submit("one", "r1", "-42", "text"), "pending")
        self.assertEqual(self.store.submit("one", "r1", "-42", "text"), "pending")
        self.assertEqual(self.store.submit("one", "r1", "-42", "different"), "conflict")
        self.assertEqual(self.store.claim("one"), ("r1", "-42", "text"))
        self.store.close()
        self.store = Store(self.path)
        self.store.recover()
        self.assertEqual(self.store.claim("one"), ("r1", "-42", "text"))
        self.store.finish("one", "r1", retry=True)
        self.store.allow("one", "-42", False)
        self.assertIsNone(self.store.claim("one"))
        self.assertEqual(self.store.db.execute("SELECT state FROM jobs").fetchone()[0], "rejected")

    def test_publication_survives_restart_until_confirmation(self):
        self.store.submit("one", "r2", "5", "text")
        item = self.store.next_publication()
        self.assertEqual(json.loads(item[2])["error_code"], "chat_not_allowed")
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.next_publication(), item)
        self.store.publication_confirmed(item[0])
        self.assertIsNone(self.store.next_publication())


if __name__ == "__main__":
    unittest.main()
