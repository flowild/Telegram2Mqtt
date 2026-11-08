"""Local configuration UI."""
import base64
import hashlib
import hmac
import html
import os
import secrets
import sqlite3
import subprocess
import re
import tempfile
import ssl
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from telegram2mqtt.store import Store, BOT_ID, CHAT_ID
from telegram2mqtt import test_messaging

DATA = Path(os.environ.get("T2M_DATA", "/var/lib/telegram2mqtt"))
SESSIONS = {}
FAILURES = {}


def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000)
    return base64.b64encode(salt + digest).decode()


def check_password(password, encoded):
    raw = base64.b64decode(encoded)
    return hmac.compare_digest(password_hash(password, raw[:16]), encoded)


def initialize():
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    store = Store(DATA / "state.db")
    store.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    row = store.db.execute("SELECT value FROM settings WHERE key='admin_hash'").fetchone()
    if not row:
        initial = secrets.token_urlsafe(24)
        path = DATA / "initial-admin-password"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(initial + "\n")
        with store.db:
            store.db.execute("INSERT INTO settings VALUES('admin_hash',?)", (password_hash(initial),))
    store.db.close()


def field(name, label, kind="text", value=""):
    return f'<label>{label}<input name="{name}" type="{kind}" value="{html.escape(value, quote=True)}" autocomplete="off"></label>'


def bridge_diagnostics():
    """Read only recognized, non-sensitive bridge messages from the journal."""
    try:
        status = subprocess.run(["systemctl", "is-active", "telegram2mqtt-bridge.service"],
                                capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        status = "unbekannt"
    if status not in ("active", "inactive", "failed", "activating", "deactivating"):
        status = "unbekannt"
    try:
        lines = (DATA / "bridge-diagnostics.log").read_text(encoding="utf-8").splitlines()
        return status, lines
    except OSError:
        return status, None


def collect_bridge_log():
    """Export a filtered journal snapshot without granting the web user journal access."""
    try:
        result = subprocess.run(["journalctl", "-u", "telegram2mqtt-bridge.service", "-n", "100",
                                 "--no-pager", "-o", "cat", "--quiet"],
                                capture_output=True, text=True, timeout=5)
        if result.returncode:
            raise RuntimeError("Journal nicht verfügbar")
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Journal nicht verfügbar")
    safe = re.compile(r"^(?:INFO MQTT verbunden|WARNING MQTT (?:Verbindung abgelehnt|getrennt|Abonnement abgelehnt|Verbindung fehlgeschlagen|Auftrag konnte nicht gespeichert werden; Verbindung wird getrennt)|WARNING Bridge-Verarbeitung vorübergehend fehlgeschlagen|WARNING Telegram-(?:Empfang fehlgeschlagen für Bot [a-zA-Z0-9_-]{1,64} \((?:conflict|retry|permanent)\)|Empfang für Bot [a-zA-Z0-9_-]{1,64} bis Dienstneustart angehalten|Update konnte nicht gespeichert werden für Bot [a-zA-Z0-9_-]{1,64}))$")
    lines = [line for line in result.stdout.splitlines() if safe.fullmatch(line)]
    target = DATA / "bridge-diagnostics.log"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=DATA, delete=False) as temporary:
        temporary.write('\n'.join(lines))
        os.fchmod(temporary.fileno(), 0o644)
    os.replace(temporary.name, target)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def response(self, body, status=200, cookie=None):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def session(self):
        try:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            sid = cookie["sid"].value
            data = SESSIONS.get(sid)
            if data and data[1] > time.monotonic():
                return sid, data[0]
        except (KeyError, ValueError):
            pass
        return None, None

    def render(self, content):
        return '''<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Telegram2Mqtt</title><style>body{font:16px system-ui;background:#f3f5f8;color:#142336;margin:0}main{max-width:900px;margin:auto;padding:32px 20px}h1{margin-bottom:4px}section{background:white;padding:22px;border-radius:12px;margin:18px 0;box-shadow:0 2px 12px #172b4d12}label{display:block;margin:12px 0}input{box-sizing:border-box;display:block;padding:10px;width:100%;margin-top:5px;border:1px solid #aab7c4;border-radius:6px}button{padding:10px 18px;background:#175bc2;color:white;border:0;border-radius:6px;cursor:pointer}.notice{background:#fff3ce;padding:14px;border-radius:6px}small{color:#526170}li{margin:8px 0}form.inline{display:inline}</style><main><h1>Telegram2Mqtt</h1><small>Lokale Verwaltung</small>''' + content + '</main></html>'

    def form(self, action, inner, csrf, label="Speichern"):
        return f'<form method="post" action="/{action}"><input type="hidden" name="csrf" value="{csrf}">{inner}<button>{label}</button></form>'

    def do_GET(self):
        sid, csrf = self.session()
        url = urlsplit(self.path)
        if url.path == '/test-status':
            test = test_messaging.status(parse_qs(url.query).get('id', [''])[0])
            if not sid or not test or test['owner'] != sid:
                return self.response('Nicht gefunden', 404)
            content = '<section><h2>Nachrichtentest</h2><p>' + html.escape(test['status']) + '</p>'
            if test['direction'] == 'in':
                content += '<p>Nach Bereitschaft diesen Text innerhalb von 90 Sekunden im freigegebenen Telegram-Chat an den ausgewählten Bot senden:</p><p><code>' + html.escape(test['token']) + '</code></p>'
            content += '<p>Bot: ' + html.escape(test['bot']) + ' · Chat: ' + html.escape(test['chat']) + '</p><p><a href="' + html.escape(self.path, quote=True) + '">Status aktualisieren</a> · <a href="/">Zurück</a></p></section>'
            return self.response(self.render(content))
        if self.path != "/":
            return self.response("Nicht gefunden", 404)
        if not sid:
            return self.response(self.render('<section><h2>Anmelden</h2><form method="post" action="/login">' + field("password", "Passwort", "password") + '<button>Anmelden</button></form></section>'))
        store = Store(DATA / "state.db")
        settings = dict(store.db.execute("SELECT key,value FROM settings WHERE key IN ('mqtt_host','mqtt_port','mqtt_tls')"))
        bots = list(store.db.execute("SELECT id FROM bots ORDER BY id"))
        chats = list(store.db.execute("SELECT bot_id,chat_id,allowed,label FROM chats ORDER BY bot_id,chat_id"))
        job_counts = list(store.db.execute("SELECT state,COUNT(*) FROM jobs GROUP BY state ORDER BY state"))
        outbox_count = store.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        store.close()
        status, log_lines = bridge_diagnostics()
        esc = html.escape
        content = '<p class="notice">Die Brücke läuft als separater Dienst. Verbindungszustand und Fehler stehen im Dienstprotokoll.</p>'
        content += '<section><h2>Diagnose</h2><p>Bridge-Dienst: <strong>' + esc(status) + '</strong> (Systemdienst, kein Telegram-Verbindungsnachweis). MQTT-Verbindungsereignisse stehen im Protokoll.</p>'
        content += '<p>Ausstehende MQTT-Veröffentlichungen: ' + str(outbox_count) + '</p><p>Telegram-Aufträge nach Status: ' + (', '.join(esc(state) + ': ' + str(count) for state, count in job_counts) or 'keine') + '</p>'
        content += '<p>Aktualisierung beim Neuladen. Das Protokoll zeigt erkannte Meldungen aus den letzten 100 Journal-Einträgen; Nachrichteninhalte werden nicht angezeigt.</p>'
        content += '<pre style="white-space:pre-wrap;overflow-wrap:anywhere">' + esc('\n'.join(log_lines) if log_lines else ('Keine passenden Meldungen oder Journal nicht lesbar.' if log_lines is not None else 'Journal nicht verfügbar.')) + '</pre></section>'
        content += '<section><h2>MQTT-Topics</h2><p>MQTT 5, QoS 1. Nur das Status-Topic ist retained; Sendeaufträge mit Retain werden verworfen.</p><ul><li><code>telegram2mqtt/v1/+/command/send</code> – abonniertes Sende-Topic</li><li><code>telegram2mqtt/v1/status</code> – MQTT-Status, nicht Telegram-Empfang</li></ul>'
        for (bot,) in bots:
            prefix = 'telegram2mqtt/v1/' + esc(bot)
            content += '<h3>Bot ' + esc(bot) + '</h3><ul><li><code>' + prefix + '/command/send</code> – Sendeauftrag</li><li><code>' + prefix + '/event/message</code> – empfangene Nachricht</li><li><code>' + prefix + '/event/result</code> – Auftragsergebnis</li></ul>'
        content += '<p>Sendeauftrag: <code>{"request_id":"test-1","chat_id":"123456789","text":"Hallo"}</code>. Der Chat muss für den Bot freigegeben sein.</p></section>'
        tls_options = '<label>MQTT-TLS<select name="tls"><option value="0"' + (' selected' if settings.get('mqtt_tls') != '1' else '') + '>Aus</option><option value="1"' + (' selected' if settings.get('mqtt_tls') == '1' else '') + '>An</option></select></label>'
        content += '<section><h2>MQTT-Broker</h2><p>Das Passwort bleibt leer, wenn es unverändert bleiben soll.</p>' + self.form('mqtt', field('host','Server',value=settings.get('mqtt_host','')) + field('port','Port',value=settings.get('mqtt_port','1883')) + field('user','Benutzername (leer lassen zum Beibehalten)') + field('password','Passwort','password') + tls_options,csrf) + '</section>'
        content += '<section><h2>Telegram-Bots</h2><ul>' + ''.join('<li>' + esc(b[0]) + self.form('bot-remove-confirm', '<input type="hidden" name="id" value="' + esc(b[0], quote=True) + '">', csrf, 'Entfernen') + '</li>' for b in bots) + '</ul>' + self.form('bot', field('id','Bot-ID (Buchstaben, Zahlen, _ oder -)') + field('token','Bot-Token','password'),csrf,'Bot hinzufügen') + '</section>'
        content += '<section><h2>Chat-Freigaben</h2><ul>' + ''.join('<li>' + esc(b) + ' · ' + esc(c) + ' · ' + ('freigegeben' if a else 'nicht freigegeben') + ' · ' + esc(l) + '</li>' for b,c,a,l in chats) + '</ul>' + self.form('chat',field('bot','Bot-ID') + field('chat','Chat-ID') + '<label>Aktion<select name="allowed"><option value="1">Freigeben</option><option value="0">Sperren</option></select></label>',csrf) + '</section>'
        content += '<section><h2>Nachrichten testen</h2><p>Bot und freigegebene Chat-ID auswählen. Beim Empfangstest anschließend den angezeigten Text in Telegram senden.</p>'
        options = ''.join('<option value="' + esc(b + ':' + c, quote=True) + '">' + esc(b + ' · ' + c) + '</option>' for b,c,a,l in chats if a)
        if options:
            selector = '<label>Bot und Chat<select name="target">' + options + '</select></label>'
            content += self.form('test-out', selector, csrf, 'MQTT → Telegram testen') + self.form('test-in', selector, csrf, 'Telegram → MQTT testen')
        else:
            content += '<p>Zuerst einen Chat für einen Bot freigeben.</p>'
        content += '</section>'
        content += '<section><h2>Passwort ändern</h2>' + self.form('password',field('password','Neues Passwort (mindestens 6 Zeichen)','password'),csrf) + '</section>' + self.form('logout','',csrf,'Abmelden')
        self.response(self.render(content))

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 16384:
                return self.response("Ungültige Anfrage", 400)
            form = parse_qs(self.rfile.read(size).decode("utf-8"), keep_blank_values=True, max_num_fields=12)
            get = lambda name: form.get(name, [""])[0]
            if self.path == "/login":
                now = time.monotonic()
                ip = self.client_address[0]
                attempts = [t for t in FAILURES.get(ip, []) if now - t < 300]
                if len(attempts) >= 10:
                    return self.response("Zu viele Anmeldeversuche. Bitte später erneut versuchen.", 429)
                store = Store(DATA / "state.db")
                encoded = store.db.execute("SELECT value FROM settings WHERE key='admin_hash'").fetchone()[0]
                store.close()
                if not check_password(get("password"), encoded):
                    FAILURES[ip] = attempts + [now]
                    return self.response("Anmeldung fehlgeschlagen", 403)
                FAILURES.pop(ip, None)
                sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                SESSIONS[sid] = (csrf, now + 3600)
                return self.redirect(f"sid={sid}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=3600")
            sid, csrf = self.session()
            if not sid or not hmac.compare_digest(csrf, get("csrf")):
                return self.response("Nicht autorisiert", 403)
            store = Store(DATA / "state.db")
            try:
                if self.path == "/mqtt":
                    host, port = get("host").strip(), int(get("port"))
                    if not host or len(host) > 253 or not 1 <= port <= 65535:
                        raise ValueError()
                    pairs = [("mqtt_host", host), ("mqtt_port", str(port)), ("mqtt_tls", "1" if get("tls") == "1" else "0")]
                    if get("user"):
                        pairs.append(("mqtt_user", get("user")))
                    if get("password"):
                        pairs.append(("mqtt_password", get("password")))
                    with store.db:
                        store.db.executemany("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", pairs)
                elif self.path == "/bot":
                    store.add_bot(get("id"), get("token"))
                elif self.path in ('/test-in', '/test-out'):
                    parts = get('target').split(':')
                    if len(parts) != 2 or not store.db.execute('SELECT 1 FROM chats WHERE bot_id=? AND chat_id=? AND allowed=1', parts).fetchone():
                        raise ValueError()
                    settings = dict(store.db.execute("SELECT key,value FROM settings WHERE key LIKE 'mqtt_%'"))
                    if not settings.get('mqtt_host'):
                        return self.response(self.render('<section><p>Bitte zuerst den MQTT-Broker konfigurieren.</p><a href="/">Zurück</a></section>'), 400)
                    test_id = test_messaging.start(settings, parts[0], parts[1], 'in' if self.path == '/test-in' else 'out', sid)
                    self.send_response(303)
                    self.send_header('Location', '/test-status?id=' + test_id)
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    return
                elif self.path == "/bot-remove-confirm":
                    bot = get("id")
                    if not BOT_ID.fullmatch(bot) or not store.db.execute("SELECT 1 FROM bots WHERE id=?", (bot,)).fetchone():
                        raise ValueError()
                    content = '<section><h2>Bot entfernen: ' + html.escape(bot) + '</h2><p>Token, Chat-Freigaben und abgeschlossene Aufträge werden gelöscht. Bereits vorgemerkte MQTT-Ereignisse bleiben erhalten. Ausstehende oder laufende Aufträge verhindern das Entfernen; bereits begonnener Telegram-Empfang kann noch kurz laufen.</p>'
                    content += self.form('bot-remove', '<input type="hidden" name="id" value="' + html.escape(bot, quote=True) + '">', csrf, 'Bot endgültig entfernen') + '<p><a href="/">Abbrechen</a></p></section>'
                    return self.response(self.render(content))
                elif self.path == "/bot-remove":
                    try:
                        store.remove_bot(get("id"))
                    except ValueError:
                        return self.response(self.render('<section><p>Bot nicht gefunden oder es gibt noch ausstehende oder laufende Aufträge. Bitte prüfen und erneut versuchen.</p><a href="/">Zurück</a></section>'), 400)
                elif self.path == "/chat":
                    if get("allowed") not in ("0", "1"):
                        raise ValueError()
                    store.allow(get("bot"), get("chat"), get("allowed") == "1")
                elif self.path == "/password":
                    if len(get("password")) < 6:
                        raise ValueError()
                    with store.db:
                        store.db.execute("UPDATE settings SET value=? WHERE key='admin_hash'", (password_hash(get("password")),))
                    (DATA / "initial-admin-password").unlink(missing_ok=True)
                    SESSIONS.clear()
                elif self.path == "/logout":
                    SESSIONS.pop(sid, None)
                else:
                    return self.response("Nicht gefunden", 404)
            finally:
                store.close()
            self.redirect()
        except (ValueError, UnicodeError, sqlite3.Error):
            self.response("Eingabe ungültig oder Eintrag bereits vorhanden.", 400)

    def redirect(self, cookie=None):
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()


def main():
    os.umask(0o077)
    initialize()
    server = HTTPServer((os.environ.get("T2M_HOST", "0.0.0.0"), int(os.environ.get("T2M_PORT", "8443"))), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(os.environ.get("T2M_CERT", str(DATA / "server.crt")), os.environ.get("T2M_KEY", str(DATA / "server.key")))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--collect-bridge-log"]:
        collect_bridge_log()
    else:
        main()
