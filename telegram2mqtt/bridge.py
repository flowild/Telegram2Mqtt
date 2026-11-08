"""Telegram polling and MQTT 5 bridge. No secrets or message bodies are logged."""
import json
import logging
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from paho.mqtt.subscribeoptions import SubscribeOptions
from telegram2mqtt.store import Store

DATA = Path(os.environ.get("T2M_DATA", "/var/lib/telegram2mqtt"))
LOG = logging.getLogger("bridge")
POLLING_BLOCKED = set()


def api(token, method, payload):
    request = urllib.request.Request("https://api.telegram.org/bot" + token + "/" + method,
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            result = json.load(response)
        return result.get("result"), None
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            return None, "conflict"
        if exc.code == 429 or exc.code >= 500:
            return None, "retry"
        return None, "permanent"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None, "retry"


def config():
    store = Store(DATA / "state.db")
    try:
        settings = dict(store.db.execute("SELECT key,value FROM settings WHERE key LIKE 'mqtt_%'"))
        bots = list(store.db.execute("SELECT id,token FROM bots ORDER BY id"))
        return settings, bots
    finally:
        store.close()


def bot_loop(bot, token):
    while True:
        store = Store(DATA / "state.db")
        try:
            row = store.db.execute("SELECT token,offset FROM bots WHERE id=?", (bot,)).fetchone()
            if not row or row[0] != token:
                return
            updates, error = api(token, "getUpdates", {"offset": row[1], "timeout": 20,
                                                         "allowed_updates": ["message"]})
            if error:
                LOG.warning("Telegram-Empfang fehlgeschlagen für Bot %s (%s)", bot, error)
                if error == "conflict":
                    POLLING_BLOCKED.add(bot)
                    LOG.warning("Telegram-Empfang für Bot %s bis Dienstneustart angehalten", bot)
                    return
                time.sleep(10)
                continue
            for update in updates:
                update_id = update.get("update_id")
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                if isinstance(chat_id, int):
                    label = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
                    store.ingest_update(bot, update_id, str(chat_id), message.get("text"), message.get("date"), str(label))
                else:
                    with store.db:
                        store.db.execute("UPDATE bots SET offset=MAX(offset,?) WHERE id=?", (update_id + 1, bot))
        except (sqlite3.Error, ValueError, TypeError, KeyError):
            LOG.warning("Telegram-Update konnte nicht gespeichert werden für Bot %s", bot)
            time.sleep(5)
        finally:
            store.close()


class Bridge:
    def __init__(self):
        self.client = None
        self.settings = None
        self.workers = {}
        self.connected = False
        self.subscription_ready = False
        self.reset_requested = False
        store = Store(DATA / "state.db")
        store.recover()
        store.close()

    def on_connect(self, client, userdata, flags, reason, properties):
        self.connected = not reason.is_failure
        self.subscription_ready = False
        if not self.connected:
            LOG.warning("MQTT-Verbindung abgelehnt")
            return
        options = SubscribeOptions(qos=1, retainAsPublished=True)
        client.subscribe("telegram2mqtt/v1/+/command/send", options=options)
        client.publish("telegram2mqtt/v1/status", '{"status":"online"}', qos=1, retain=True)
        LOG.info("MQTT verbunden")

    def on_disconnect(self, client, userdata, flags, reason, properties):
        self.connected = False
        self.subscription_ready = False
        LOG.warning("MQTT getrennt")

    def on_subscribe(self, client, userdata, mid, reasons, properties):
        self.subscription_ready = bool(reasons) and not any(reason.is_failure for reason in reasons)
        if not self.subscription_ready:
            LOG.warning("MQTT-Abonnement abgelehnt")

    def on_message(self, client, userdata, message):
        # Invalid, retained and uncorrelatable messages are deliberately discarded.
        try:
            parts = message.topic.split('/')
            if len(parts) != 5 or message.retain or len(message.payload) > 16384:
                client.ack(message.mid, message.qos)
                return
            payload = json.loads(message.payload.decode('utf-8'))
            if not isinstance(payload, dict):
                raise ValueError()
            store = Store(DATA / "state.db")
            try:
                if not store.db.execute("SELECT 1 FROM bots WHERE id=?", (parts[2],)).fetchone():
                    client.ack(message.mid, message.qos)
                    return
                store.submit(parts[2], payload.get("request_id"), payload.get("chat_id"), payload.get("text"))
            finally:
                store.close()
            client.ack(message.mid, message.qos)
        except (ValueError, UnicodeError, TypeError):
            client.ack(message.mid, message.qos)
        except sqlite3.Error:
            LOG.warning("MQTT-Auftrag konnte nicht gespeichert werden; Verbindung wird getrennt")
            self.reset_requested = True
            client.disconnect()

    def connect(self, settings):
        self.reset_requested = False
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()
        self.connected = False
        self.subscription_ready = False
        self.client = None
        if not settings.get("mqtt_host"):
            return
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="telegram2mqtt-bridge", protocol=mqtt.MQTTv5, manual_ack=True)
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_subscribe = self.on_subscribe
        client.on_message = self.on_message
        client.will_set("telegram2mqtt/v1/status", '{"status":"offline"}', qos=1, retain=True)
        if settings.get("mqtt_user"):
            client.username_pw_set(settings["mqtt_user"], settings.get("mqtt_password"))
        if settings.get("mqtt_tls") == "1":
            client.tls_set()
        properties = Properties(PacketTypes.CONNECT)
        properties.SessionExpiryInterval = 604800
        try:
            client.connect(settings["mqtt_host"], int(settings.get("mqtt_port", "1883")), 60, clean_start=False, properties=properties)
            client.loop_start()
            self.client = client
        except (OSError, ValueError):
            LOG.warning("MQTT-Verbindung fehlgeschlagen")

    def run(self):
        while True:
            try:
                settings, bots = config()
                if self.reset_requested or settings != self.settings or (self.client is None and settings.get("mqtt_host")):
                    self.connect(settings)
                    self.settings = settings
                for bot, token in bots:
                    if bot in POLLING_BLOCKED:
                        continue
                    worker = self.workers.get(bot)
                    if not worker or not worker.is_alive():
                        worker = threading.Thread(target=bot_loop, args=(bot, token), daemon=True)
                        worker.start()
                        self.workers[bot] = worker
                self.step(bots)
            except (sqlite3.Error, ValueError, OSError):
                LOG.warning("Bridge-Verarbeitung vorübergehend fehlgeschlagen")
            time.sleep(10)

    def step(self, bots):
        store = Store(DATA / "state.db")
        try:
            if self.client and self.connected:
                item = store.next_publication()
                if item:
                    info = self.client.publish(item[1], item[2], qos=1, retain=False)
                    if info.rc == mqtt.MQTT_ERR_SUCCESS:
                        try:
                            info.wait_for_publish(timeout=5)
                            if info.is_published():
                                store.publication_confirmed(item[0])
                        except (ValueError, RuntimeError):
                            pass
            for bot, token in bots:
                job = store.claim(bot)
                if not job:
                    continue
                request_id, chat_id, text = job
                result, error = api(token, "sendMessage", {"chat_id": chat_id, "text": text})
                if error in ("permanent", "conflict"):
                    store.fail(bot, request_id)
                elif error:
                    store.finish(bot, request_id, retry=True)
                else:
                    if isinstance(result, dict) and "message_id" in result:
                        store.finish(bot, request_id, message_id=result["message_id"])
                    else:
                        store.finish(bot, request_id, retry=True)
        finally:
            store.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    Bridge().run()


if __name__ == '__main__':
    main()
