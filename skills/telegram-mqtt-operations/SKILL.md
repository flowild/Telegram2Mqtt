---
name: telegram-mqtt-operations
description: Richtet die Telegram–MQTT-Brücke im Proxmox-LXC ein und unterstützt Konfiguration, Betrieb und Diagnose nach konkreter Beauftragung.
---

# Betrieb der Telegram–MQTT-Brücke

Lies [AGENTS.md](../../AGENTS.md) und die tatsächlich vorhandene Installations- und Betriebsdokumentation. Unterscheide Planung von implementierten Funktionen und bereits vorhandener Infrastruktur.

- Kläre bei der Einrichtung die benötigten Proxmox-, LXC-, Netzwerk- und MQTT-Angaben anhand der tatsächlichen Umgebung. Ein Debian-LXC mit systemd ist ein Vorschlag, keine bereits getroffene Tatsache. Setze die externe Infrastruktur nur im autorisierten Umfang auf oder ändere sie.
- Stelle automatischen Start, persistente Konfiguration und Warteschlange, nachvollziehbare Dienst-Logs sowie die Wiederverbindung zu MQTT und Telegram sicher. Prüfe nach Änderungen Dienstzustand, Erreichbarkeit und das Zusammenspiel anhand eines geeigneten Test-Bots.
- Schütze das Webinterface im lokalen Netz mit einem Passwort. Begrenze Zugriff auf gespeicherte Zugangsdaten; gib Tokens, Passwörter und API-Schlüssel nicht in Logs, Ausgaben, Beispielen oder Versionsverwaltung aus.
- Übernimm einen bestehenden Home-Assistant-Bot nicht unbemerkt: Das Umstellen des Empfangs kann dessen bestehende Integration beeinträchtigen. Plane die Migration mit dem Nutzer.
- Dokumentiere tatsächliche Installations-, Update-, Backup- und Wiederherstellungsschritte sowie relevante Änderungen an Einstellungen und Betrieb. Halte Projektanweisungen und diesen Skill aktuell.
