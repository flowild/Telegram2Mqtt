---
name: telegram-mqtt-operations
description: Richtet die Telegram–MQTT-Brücke im Proxmox-LXC ein und unterstützt Konfiguration, Betrieb und Diagnose nach konkreter Beauftragung.
---

# Betrieb der Telegram–MQTT-Brücke

Lies [AGENTS.md](../../AGENTS.md) und die tatsächlich vorhandene Installations- und Betriebsdokumentation. Unterscheide Planung von implementierten Funktionen und bereits vorhandener Infrastruktur.

Der eingerichtete Debian-13-LXC und sein Proxmox-Ziel sind in AGENTS.md dokumentiert. Konfigurationsoberfläche und Bridge laufen im Container; der Telegram-Empfang ist nach einem Konflikt mit einem anderen Empfänger angehalten. Betriebsdetails und Erstzugang stehen in [BETRIEB.md](../../BETRIEB.md).

Für SSH den in AGENTS.md dokumentierten Schlüssel und die dort genannte Hostschlüsseldatei verwenden; die per DHCP vergebene Adresse vor Bedarf prüfen. Das ursprünglich erzeugte Root-Passwort wurde offengelegt und ist nicht mehr zu verwenden.

- Kläre bei der Einrichtung die benötigten Proxmox-, LXC-, Netzwerk- und MQTT-Angaben anhand der tatsächlichen Umgebung. Der Dienst und seine systemd-Einrichtung sind vorhanden. Setze die externe Infrastruktur nur im autorisierten Umfang auf oder ändere sie.
- Stelle automatischen Start, persistente Konfiguration und Warteschlange, nachvollziehbare Dienst-Logs sowie die Wiederverbindung zu MQTT und Telegram sicher. Prüfe nach Änderungen Dienstzustand, Erreichbarkeit und das Zusammenspiel anhand eines geeigneten Test-Bots.
- Schütze das Webinterface im lokalen Netz mit einem Passwort. Begrenze Zugriff auf gespeicherte Zugangsdaten; gib Tokens, Passwörter und API-Schlüssel nicht in Logs, Ausgaben, Beispielen oder Versionsverwaltung aus.
- Übernimm einen bestehenden Home-Assistant-Bot nicht unbemerkt: Das Umstellen des Empfangs kann dessen bestehende Integration beeinträchtigen. Plane die Migration mit dem Nutzer.
- Dokumentiere tatsächliche Installations-, Update-, Backup- und Wiederherstellungsschritte sowie relevante Änderungen an Einstellungen und Betrieb. Halte Projektanweisungen und diesen Skill aktuell.

Installiere jede Projektänderung nach passenden Prüfungen gemäß AGENTS.md auf dem vorgesehenen LXC und prüfe den Dienst. Installation und Erstzugang sind in BETRIEB.md beschrieben. Der tatsächliche MQTT-Vertrag steht in MQTT.md; Telegram-Empfangskonflikte vor Neustart gezielt klären.

Die Webdiagnose zeigt Dienstzustand, Warteschlangenzahlen, Topics und gefilterte Journalmeldungen aus einem zeitgesteuerten Export. Der Dienstzustand ist kein Nachweis einer Telegram- oder MQTT-Verbindung; für vollständige Fehlerdiagnose das Bridge-Journal verwenden.

Die Oberfläche bietet Nachrichtentests für freigegebene Chats: MQTT-Auftrag mit Ergebnisbeobachtung und Telegram-Empfang durch Senden eines angezeigten Testtexts. Ablauf und Grenzen stehen in BETRIEB.md.

Das Administrationspasswort der Oberfläche hat eine Mindestlänge von sechs Zeichen.
