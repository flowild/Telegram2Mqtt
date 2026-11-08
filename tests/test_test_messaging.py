import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from telegram2mqtt import test_messaging


class Client:
    def __init__(self, *args, **kwargs):
        self.topic = None
        self.payload = None

    def connect(self, *args):
        pass

    def loop_start(self):
        self.on_connect(self, None, None, SimpleNamespace(is_failure=False), None)

    def subscribe(self, topic, options):
        self.topic = topic
        self.on_subscribe(self, None, 1, [SimpleNamespace(is_failure=False)], None)

    def publish(self, topic, payload, qos, retain):
        self.payload = json.loads(payload)
        self.command = (topic, qos, retain)
        result = {'request_id': self.payload['request_id'], 'status': 'sent'}
        self.on_message(self, None, SimpleNamespace(payload=json.dumps(result).encode()))
        return SimpleNamespace(rc=0)

    def disconnect(self):
        pass

    def loop_stop(self):
        pass


class MessagingTests(unittest.TestCase):
    def test_outgoing_uses_mqtt_and_waits_for_matching_result(self):
        client = Client()
        test_messaging.TESTS['id'] = {'status': ''}
        with patch('paho.mqtt.client.Client', return_value=client):
            test_messaging._run('id', {'mqtt_host': 'broker'}, 'bot', '123', 'out', 'token')
        self.assertEqual(client.topic, 'telegram2mqtt/v1/bot/event/result')
        self.assertEqual(client.command, ('telegram2mqtt/v1/bot/command/send', 1, False))
        self.assertEqual(client.payload['chat_id'], '123')
        self.assertIn('Erfolg', test_messaging.status('id')['status'])

    def test_incoming_waits_for_matching_telegram_event(self):
        client = Client()
        original = client.subscribe
        def subscribe(topic, options):
            original(topic, options)
            def send():
                payload = {'chat_id': '123', 'text': 'token'}
                client.on_message(client, None, SimpleNamespace(payload=json.dumps(payload).encode()))
            threading.Timer(0.01, send).start()
        client.subscribe = subscribe
        test_messaging.TESTS['id'] = {'status': ''}
        with patch('paho.mqtt.client.Client', return_value=client):
            test_messaging._run('id', {'mqtt_host': 'broker'}, 'bot', '123', 'in', 'token')
        self.assertEqual(client.topic, 'telegram2mqtt/v1/bot/event/message')
        self.assertIn('Erfolg', test_messaging.status('id')['status'])
