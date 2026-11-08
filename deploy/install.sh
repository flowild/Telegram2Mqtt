#!/bin/sh
set -eu
if [ "$(id -u)" -ne 0 ]; then echo 'Als root ausführen.' >&2; exit 1; fi
command -v python3 >/dev/null
command -v openssl >/dev/null
if ! id telegram2mqtt >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/telegram2mqtt --shell /usr/sbin/nologin telegram2mqtt
fi
install -d -m 0755 /opt/telegram2mqtt /opt/telegram2mqtt/telegram2mqtt
install -d -o telegram2mqtt -g telegram2mqtt -m 0700 /var/lib/telegram2mqtt
install -m 0644 telegram2mqtt/__init__.py telegram2mqtt/store.py telegram2mqtt/web.py /opt/telegram2mqtt/telegram2mqtt/
if [ ! -f /var/lib/telegram2mqtt/server.key ] && [ ! -f /var/lib/telegram2mqtt/server.crt ]; then
  umask 077
  openssl req -x509 -newkey rsa:3072 -nodes -keyout /var/lib/telegram2mqtt/server.key -out /var/lib/telegram2mqtt/server.crt -days 825 -subj '/CN=telegram2mqtt' >/dev/null 2>&1
  chown telegram2mqtt:telegram2mqtt /var/lib/telegram2mqtt/server.key /var/lib/telegram2mqtt/server.crt
fi
install -m 0644 deploy/telegram2mqtt.service /etc/systemd/system/telegram2mqtt.service
systemctl daemon-reload
systemctl enable telegram2mqtt.service >/dev/null
systemctl restart telegram2mqtt.service
systemctl is-active --quiet telegram2mqtt.service
