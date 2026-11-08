# Installation und Betrieb

Die Konfigurationsoberfläche 0.2.0 läuft im LXC als `telegram2mqtt.service` unter dem gleichnamigen Systembenutzer. Sie bietet eine Anmeldung sowie die lokale Verwaltung von Broker-Einstellungen, Bot-Tokens und Chat-Freigaben. Die Telegram- und MQTT-Anbindung läuft in einem separaten Bridge-Dienst.

Unter „Nachrichten testen“ einen freigegebenen Bot und Chat auswählen. Der MQTT-zu-Telegram-Test veröffentlicht einen regulären MQTT-Auftrag und wartet auf dessen Ergebnis. Beim Telegram-zu-MQTT-Test nach der Bereitschaftsmeldung den angezeigten Testtext innerhalb von 90 Sekunden an den Bot senden und den Status aktualisieren. Der Test lauscht auf das zugehörige MQTT-Ereignis. Ein Timeout beweist keinen bestimmten Fehler; ein Sendeauftrag kann danach noch in der Warteschlange stehen. Der Broker muss dem konfigurierten Benutzer die jeweiligen Test-Topics erlauben. Der Telegram-Empfangskonflikt kann den Empfangstest verhindern.

Am 08.11.2026 wurden nach elf erfolgreichen Tests `web.py` und `test_messaging.py` auf dem LXC installiert und die Oberfläche neu gestartet. Beide Dienste waren aktiv und die HTTPS-Anmeldeseite antwortete mit HTTP 200. Die Nachrichtentests wurden mit simuliertem MQTT-Broker geprüft; ein vollständiger Test mit Telegram und Broker wurde nicht ausgelöst.

Nach der Anmeldung zeigt die Oberfläche den Systemdienstzustand, Warteschlangenzahlen, die MQTT-Topics pro Bot und ein gefiltertes Bridge-Protokoll. Der Dienstzustand belegt weder eine MQTT- noch eine Telegram-Verbindung. Ein systemd-Timer aktualisiert alle 30 Sekunden den Export bekannter, nicht vertraulicher Meldungen aus den letzten 100 Journal-Einträgen; fehlende Meldungen belegen keinen fehlerfreien Betrieb. Nachrichteninhalte und Zugangsdaten werden nicht angezeigt. Für vollständige Diagnose bleibt `journalctl -u telegram2mqtt-bridge` maßgeblich. Der Dienstbenutzer erhält keinen allgemeinen Journalzugriff.

Aufruf im lokalen Netz: `https://192.168.184.85:8443/` (DHCP-Adresse kann sich ändern). Das automatisch erzeugte Zertifikat ist selbstsigniert und wird vom Browser nicht als vertrauenswürdig eingestuft. Zertifikat über einen sicheren Kanal prüfen beziehungsweise später durch ein vertrauenswürdiges Zertifikat ersetzen. Die Oberfläche darf nicht ungeschützt ins Internet freigegeben werden.

Das automatisch erzeugte erste Administrationspasswort liegt ausschließlich im Container in `/var/lib/telegram2mqtt/initial-admin-password`. Mit dem dokumentierten SSH-Schlüssel als root anmelden und diese Datei dort anzeigen; das Passwort nicht in Git, Tickets oder Chat kopieren. Nach der Anmeldung auf der Oberfläche ein eigenes Passwort mit mindestens sechs Zeichen setzen. Dabei wird die Datei entfernt. Der Anmelde-Hash wird mit PBKDF2 gespeichert; Sitzungen sind nach Neustart ungültig und laufen nach einer Stunde ab.

Am 08.11.2026 wurde die Mindestlänge nach zwölf erfolgreichen Tests durch Aktualisierung von `web.py` im LXC geändert. Die Oberfläche wurde neu gestartet, beide Dienste waren aktiv; die Passwortänderung und Anmeldung wurden mit einer isolierten Testdatenbank geprüft.

Die Datenbank `/var/lib/telegram2mqtt/state.db` enthält Broker-Passwort und Bot-Tokens im Klartext und ist durch den Dienstbenutzer und restriktive Dateirechte geschützt. Auch Backups enthalten Geheimnisse und müssen entsprechend geschützt werden. Die Weboberfläche gibt gespeicherte Zugangsdaten nicht erneut aus; leere MQTT-Zugangsfelder erhalten die vorhandenen Werte. TLS-Zertifikat und privater Schlüssel befinden sich ebenfalls im Datenverzeichnis.

Für Installation oder Aktualisierung aus einem geprüften Checkout als root im Projektverzeichnis `sh deploy/install.sh` ausführen. Das Skript benötigt Python 3, OpenSSL, systemd und das Debian-Paket python3-paho-mqtt, installiert die Programmdateien nach `/opt/telegram2mqtt`, erhält vorhandene Daten und Zertifikate und startet den Dienst neu. Status und Logs: `systemctl status telegram2mqtt` und `journalctl -u telegram2mqtt`. Bei einem Update vorab Datenverzeichnis geschützt sichern; eine Wiederherstellung wurde noch nicht erprobt. Ein vollständig getesteter Backup-Ablauf sowie Netzwerkadapter und produktive Betriebsfreigabe fehlen noch.

Das Installationsskript startet auch die Bridge neu. Bei einem bekannten Telegram-Empfangskonflikt zunächst die andere Empfangsinstanz klären; ein Neustart kann den Empfang erneut aktivieren. Der Diagnoseexport läuft über `telegram2mqtt-diagnostics.timer` und `telegram2mqtt-diagnostics.service`.

Am 08.11.2026 wurden die aktualisierte `web.py` und die beiden Diagnose-Units nach erfolgreichen Tests auf dem LXC installiert. Der Timer wurde aktiviert und der Export einmal gestartet; nur die Oberfläche wurde neu gestartet, die laufende Bridge nicht. Der Export war für den Dienstbenutzer lesbar und die HTTPS-Anmeldeseite erreichbar.

## Bridge 0.2.0

Bots können in der Oberfläche nach einer Bestätigung entfernt werden. Dabei werden Token, Chat-Freigaben und abgeschlossene Aufträge gelöscht; ausstehende oder laufende Aufträge verhindern das Entfernen. Bereits vorgemerkte MQTT-Ereignisse bleiben erhalten. Ein laufender Telegram-Empfang kann noch kurz auslaufen.

Am 08.11.2026 wurden nach acht erfolgreichen Tests `store.py` und `web.py` im LXC aktualisiert und nur die Oberfläche neu gestartet. Beide Dienste meldeten sich aktiv; die HTTPS-Anmeldeseite war erreichbar. Der Löschablauf wurde mit einer isolierten Testdatenbank geprüft, kein vorhandener Bot gelöscht.

Der Dienst `telegram2mqtt-bridge.service` nutzt die in der Oberfläche gespeicherte Konfiguration und benötigt das Debian-Paket `python3-paho-mqtt` (2.x). Die konkrete MQTT-Schnittstelle und bekannte Grenzen stehen in [MQTT.md](MQTT.md). Protokoll und Fehler: `journalctl -u telegram2mqtt-bridge`. Die Oberfläche und die Bridge sind getrennte Dienste. Die Bridge erkennt Konfigurationsänderungen nach kurzer Zeit; bei Telegram-Empfangskonflikt muss zunächst die Ursache geklärt werden. Ein Testauftrag über den konfigurierten Broker wurde von Telegram mit `sent` bestätigt; der Telegram-Empfang meldete einen Konflikt mit einer anderen Empfangsinstanz und ist angehalten.
