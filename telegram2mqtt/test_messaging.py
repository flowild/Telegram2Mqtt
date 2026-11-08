"""Short-lived MQTT clients for the interactive connection tests."""
import json
import threading
import time
import uuid

TESTS = {}
LOCK = threading.Lock()


def start(settings, bot, chat, direction, owner):
    test_id = uuid.uuid4().hex
    token = 'T2M-Test-' + test_id[:12]
    with LOCK:
        now = time.monotonic()
        for key in list(TESTS):
            if now - TESTS[key]['created'] > 600:
                del TESTS[key]
        TESTS[test_id] = {'created': now, 'status': 'Verbindung zum MQTT-Broker wird aufgebaut',
                          'token': token, 'direction': direction, 'bot': bot, 'chat': chat, 'owner': owner}
    threading.Thread(target=_run, args=(test_id, settings, bot, chat, direction, token), daemon=True).start()
    return test_id


def status(test_id):
    with LOCK:
        return dict(TESTS[test_id]) if test_id in TESTS else None


def _set(test_id, message):
    with LOCK:
        if test_id in TESTS:
            TESTS[test_id]['status'] = message


def _run(test_id, settings, bot, chat, direction, token):
    client = None
    try:
        import paho.mqtt.client as mqtt
        from paho.mqtt.subscribeoptions import SubscribeOptions
        connected, subscribed, completed = threading.Event(), threading.Event(), threading.Event()
        failure = []
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='t2m-test-' + test_id, protocol=mqtt.MQTTv5)
        if settings.get('mqtt_user'):
            client.username_pw_set(settings['mqtt_user'], settings.get('mqtt_password'))
        if settings.get('mqtt_tls') == '1':
            client.tls_set()
        topic = f'telegram2mqtt/v1/{bot}/event/' + ('result' if direction == 'out' else 'message')

        def on_connect(client, userdata, flags, reason, properties):
            if reason.is_failure:
                failure.append('MQTT-Verbindung abgelehnt')
            else:
                client.subscribe(topic, options=SubscribeOptions(qos=1))
            connected.set()

        def on_subscribe(client, userdata, mid, reasons, properties):
            if not reasons or any(reason.is_failure for reason in reasons):
                failure.append('MQTT-Abonnement abgelehnt')
            subscribed.set()

        def on_message(client, userdata, message):
            try:
                data = json.loads(message.payload.decode('utf-8'))
                if direction == 'in' and data.get('chat_id') == chat and data.get('text') == token:
                    _set(test_id, 'Erfolg: Telegram-Nachricht über MQTT empfangen')
                    completed.set()
                elif direction == 'out' and data.get('request_id') == test_id:
                    state = data.get('status')
                    if state in ('sent', 'failed', 'rejected'):
                        _set(test_id, {'sent': 'Erfolg: Telegram hat die Nachricht angenommen', 'failed': 'Telegram-Versand fehlgeschlagen', 'rejected': 'Auftrag wurde abgelehnt'}[state])
                        completed.set()
            except (ValueError, UnicodeError, AttributeError):
                pass

        client.on_connect, client.on_subscribe, client.on_message = on_connect, on_subscribe, on_message
        client.connect(settings['mqtt_host'], int(settings.get('mqtt_port', '1883')), 30)
        client.loop_start()
        if not connected.wait(8) or failure or not subscribed.wait(8) or failure:
            _set(test_id, failure[0] if failure else 'MQTT-Verbindung oder Abonnement nicht bestätigt')
            return
        if direction == 'out':
            payload = json.dumps({'request_id': test_id, 'chat_id': chat, 'text': 'Telegram2Mqtt Testnachricht: ' + token})
            _set(test_id, 'Auftrag veröffentlicht; warte auf Telegram-Ergebnis')
            result = client.publish(f'telegram2mqtt/v1/{bot}/command/send', payload, qos=1, retain=False)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                _set(test_id, 'MQTT-Auftrag konnte nicht veröffentlicht werden')
                return
        elif not completed.is_set():
            _set(test_id, 'Bereit: Testtext jetzt in Telegram an den Bot senden')
        if not completed.wait(90):
            _set(test_id, 'Zeitüberschreitung: kein passendes Ergebnis innerhalb von 90 Sekunden; ein Sendeauftrag kann noch ausstehen')
    except (OSError, ValueError, KeyError, ImportError):
        _set(test_id, 'MQTT-Test konnte nicht gestartet werden; Broker-Konfiguration prüfen')
    finally:
        if client:
            client.disconnect()
            client.loop_stop()
