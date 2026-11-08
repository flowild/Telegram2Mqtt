import http.client
import re
import tempfile
import threading
import unittest
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


if __name__ == '__main__':
    unittest.main()
