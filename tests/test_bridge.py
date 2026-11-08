import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from telegram2mqtt import bridge
from telegram2mqtt.store import Store


class FakeClient:
    def __init__(self):
        self.acks = []
    def ack(self, mid, qos):
        self.acks.append((mid, qos))
    def disconnect(self):
        pass


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        bridge.DATA = Path(self.temp.name)
        store = Store(bridge.DATA / 'state.db')
        store.add_bot('test', 'token')
        store.allow('test', '123')
        store.close()
        self.bridge = bridge.Bridge()
        self.client = FakeClient()

    def tearDown(self):
        self.temp.cleanup()

    def message(self, payload, retain=False):
        return SimpleNamespace(topic='telegram2mqtt/v1/test/command/send', payload=json.dumps(payload).encode(), retain=retain, mid=5, qos=1)

    def test_persist_before_ack_and_retain_rejected(self):
        self.bridge.on_message(self.client, None, self.message({'request_id':'r1', 'chat_id':'123', 'text':'hello'}))
        store = Store(bridge.DATA / 'state.db')
        self.assertEqual(store.db.execute('select state from jobs').fetchone()[0], 'pending')
        store.close()
        self.assertEqual(self.client.acks, [(5, 1)])
        self.bridge.on_message(self.client, None, self.message({'request_id':'r2', 'chat_id':'123', 'text':'hello'}, True))
        store = Store(bridge.DATA / 'state.db')
        self.assertEqual(store.db.execute('select count(*) from jobs').fetchone()[0], 1)
        store.close()

    def test_delivery_and_permanent_error_are_reported(self):
        store = Store(bridge.DATA / 'state.db')
        store.submit('test', 'r1', '123', 'hello')
        store.close()
        with patch.object(bridge, 'api', return_value=({'message_id': 9}, None)):
            self.bridge.step([('test','token')])
        store = Store(bridge.DATA / 'state.db')
        self.assertEqual(store.db.execute('select state from jobs').fetchone()[0], 'sent')
        store.submit('test', 'r2', '123', 'hello')
        store.close()
        with patch.object(bridge, 'api', return_value=(None, 'permanent')):
            self.bridge.step([('test','token')])
        store = Store(bridge.DATA / 'state.db')
        self.assertEqual(store.db.execute("select state from jobs where request_id='r2'").fetchone()[0], 'failed')
        store.close()


if __name__ == '__main__':
    unittest.main()
