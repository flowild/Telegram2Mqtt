import http.client
import re
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
from http.server import HTTPServer
from urllib.parse import urlencode
from telegram2mqtt import web


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        web.DATA = Path(self.temp.name)
        web.SESSIONS.clear()
        web.FAILURES.clear()
        web.initialize()
        self.password = (web.DATA / "initial-admin-password").read_text().strip()
        self.server = HTTPServer(("127.0.0.1", 0), web.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port)

    def tearDown(self):
        self.conn.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def post(self, path, fields, cookie=""):
        self.conn.request("POST", path, urlencode(fields), {"Cookie": cookie, "Content-Type": "application/x-www-form-urlencoded"})
        response = self.conn.getresponse()
        data = response.read().decode()
        return response, data

    def test_auth_csrf_and_secret_not_returned(self):
        response, _ = self.post('/bot', {'id':'test','token':'hidden'})
        self.assertEqual(response.status, 403)
        response, _ = self.post('/login', {'password':self.password})
        self.assertEqual(response.status, 303)
        cookie = response.getheader('Set-Cookie').split(';')[0]
        self.conn.request('GET', '/', headers={'Cookie':cookie})
        response = self.conn.getresponse()
        page = response.read().decode()
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        response, _ = self.post('/bot', {'id':'test','token':'secret-token'}, cookie)
        self.assertEqual(response.status, 403)
        response, _ = self.post('/bot', {'id':'test','token':'secret-token','csrf':csrf}, cookie)
        self.assertEqual(response.status, 303)
        self.conn.request('GET', '/', headers={'Cookie':cookie})
        page = self.conn.getresponse().read().decode()
        self.assertIn('test', page)
        self.assertNotIn('secret-token', page)

    def test_password_minimum_six_characters(self):
        response, _ = self.post('/login', {'password': self.password})
        cookie = response.getheader('Set-Cookie').split(';')[0]
        self.conn.request('GET', '/', headers={'Cookie': cookie})
        page = self.conn.getresponse().read().decode()
        self.assertIn('mindestens 6 Zeichen', page)
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        response, _ = self.post('/password', {'csrf': csrf, 'password': 'abcde'}, cookie)
        self.assertEqual(response.status, 400)
        response, _ = self.post('/password', {'csrf': csrf, 'password': 'abcdef'}, cookie)
        self.assertEqual(response.status, 303)
        response, _ = self.post('/login', {'password': 'abcdef'})
        self.assertEqual(response.status, 303)

    def test_diagnostics_filters_journal_and_shows_topics_only_after_login(self):
        journal = 'INFO MQTT verbunden\nWARNING Telegram-Empfang fehlgeschlagen für Bot test (conflict)\nsecret-token\n'
        with patch('telegram2mqtt.web.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=journal)):
            web.collect_bridge_log()
        self.assertNotIn('secret-token', (web.DATA / 'bridge-diagnostics.log').read_text())
        self.conn.request('GET', '/')
        self.assertNotIn('MQTT-Topics', self.conn.getresponse().read().decode())
        response, _ = self.post('/login', {'password': self.password})
        cookie = response.getheader('Set-Cookie').split(';')[0]
        with patch('telegram2mqtt.web.subprocess.run', return_value=SimpleNamespace(stdout='active')):
            self.conn.request('GET', '/', headers={'Cookie': cookie})
            page = self.conn.getresponse().read().decode()
        self.assertIn('MQTT-Topics', page)
        self.assertIn('MQTT verbunden', page)
        self.assertIn('conflict', page)
        self.assertNotIn('secret-token', page)

    def test_remove_bot_requires_auth_and_preserves_unfinished_jobs(self):
        response, _ = self.post('/login', {'password': self.password})
        cookie = response.getheader('Set-Cookie').split(';')[0]
        self.conn.request('GET', '/', headers={'Cookie': cookie})
        page = self.conn.getresponse().read().decode()
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        store = web.Store(web.DATA / 'state.db')
        store.add_bot('test', 'token')
        store.allow('test', '123')
        store.submit('test', 'request', '123', 'hello')
        store.close()

        response, _ = self.post('/bot-remove', {'id': 'test', 'csrf': csrf})
        self.assertEqual(response.status, 403)
        response, page = self.post('/bot-remove-confirm', {'id': 'test', 'csrf': csrf}, cookie)
        self.assertEqual(response.status, 200)
        self.assertIn('Bot endgültig entfernen', page)
        response, _ = self.post('/bot-remove', {'id': 'test', 'csrf': csrf}, cookie)
        self.assertEqual(response.status, 400)
        store = web.Store(web.DATA / 'state.db')
        self.assertIsNotNone(store.db.execute("SELECT 1 FROM bots WHERE id='test'").fetchone())
        store.claim('test')
        store.finish('test', 'request', message_id=1)
        store.close()
        response, _ = self.post('/bot-remove', {'id': 'test', 'csrf': csrf}, cookie)
        self.assertEqual(response.status, 303)
        store = web.Store(web.DATA / 'state.db')
        self.assertEqual(store.db.execute('SELECT COUNT(*) FROM bots').fetchone()[0], 0)
        self.assertEqual(store.db.execute('SELECT COUNT(*) FROM chats').fetchone()[0], 0)
        self.assertEqual(store.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 0)
        self.assertGreater(store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0], 0)
        store.close()


    def test_message_tests_require_freigabe_and_session(self):
        response, _ = self.post('/login', {'password': self.password})
        cookie = response.getheader('Set-Cookie').split(';')[0]
        self.conn.request('GET', '/', headers={'Cookie': cookie})
        csrf = re.search(r'name="csrf" value="([^"]+)"', self.conn.getresponse().read().decode()).group(1)
        store = web.Store(web.DATA / 'state.db')
        store.add_bot('test', 'token')
        store.allow('test', '123')
        with store.db:
            store.db.execute("INSERT INTO settings VALUES('mqtt_host', 'broker')")
        store.close()
        with patch('telegram2mqtt.web.test_messaging.start', return_value='abc') as start:
            response, _ = self.post('/test-out', {'csrf': csrf, 'target': 'test:999'}, cookie)
            self.assertEqual(response.status, 400)
            response, _ = self.post('/test-out', {'csrf': csrf, 'target': 'test:123'}, cookie)
            self.assertEqual(response.status, 303)
            self.assertEqual(response.getheader('Location'), '/test-status?id=abc')
            self.assertEqual(start.call_args.args[1:4], ('test', '123', 'out'))

if __name__ == '__main__':
    unittest.main()
