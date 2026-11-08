---
name: telegram-mqtt-bridge
description: Entwickelt und prüft die Telegram–MQTT-Brücke dieses Projekts, einschließlich Bot-Isolation, Chat-Freigaben, Nachrichtenvertrag und zuverlässiger Zustellung.
---

# Telegram–MQTT-Brücke

Lies zuerst die Projektanforderungen in [AGENTS.md](../../AGENTS.md) und prüfe den aktuellen Code und dokumentierten MQTT-Vertrag. Die dort skizzierten Topics sind zunächst Vorschläge. Entwickle für mehrere unabhängige Bots; halte bot-spezifische Daten und Nachrichten getrennt.

- Prüfe die Chat-Freigabe vor jeder Weiterleitung eingehender Nachrichten und vor dem Versand ausgehender Aufträge. Behandle Chat-IDs als Identifikatoren, nicht als Geheimnisse; protokolliere keine Tokens oder Passwörter. Unbekannte Kontakte müssen zur Prüfung sichtbar sein, ohne ihre Inhalte an MQTT weiterzuleiten.
- Definiere und dokumentiere vor einer Integration den Nachrichtenvertrag mit Typen, Beispielen ohne Geheimnisse, Bot- und Chat-Zuordnung, Auftrags-ID, Ergebnis- und Fehlerformat sowie MQTT-QoS und Retain-Verhalten. Berücksichtige ungültige Aufträge und nicht freigegebene Chats.
- Speichere Sendeaufträge dauerhaft, bevor sie als angenommen gelten. Lege Wiederholungsstrategie und Zustand bei unklarem Sendeergebnis fest; Telegram-Duplikate bei Wiederholung sind möglich. Berücksichtige Neustarts und gleichzeitige Verarbeitung.
- Vermeide Konflikte mit einem bestehenden Telegram-Empfänger: Für Entwicklung einen separaten Bot nutzen und die Migration des bestehenden Bots gesondert planen. Ein Telegram-Bot kann nicht gleichzeitig Webhook und Polling für den Empfang nutzen.
- Prüfe relevante Änderungen anhand beobachtbaren Verhaltens: erlaubte und abgelehnte Chats, Bot-Trennung, Sendeergebnisse, Wiederanlauf der Warteschlange und Fehlerfälle. Externe Dienste bei Tests kontrolliert ersetzen, sofern echte Integration nicht erforderlich ist.
- Halte Projektanweisungen und den dokumentierten Vertrag bei funktionalen Änderungen synchron. Implementiere die spätere Home-Assistant-Integration oder direkte Gerätesteuerung nur, wenn sie gesondert beauftragt werden.

Der bisherige SQLite-Kern in `telegram2mqtt/store.py` ist isoliert und noch nicht an Telegram oder MQTT angebunden. Er wird von der Konfigurationsoberfläche genutzt. Sein Schema und Vertrag sind vorläufig; vor einer Integration Transaktionsgrenzen, Mehrläufigkeit, Fehlerbehandlung und die vollständige Umsetzung der obigen Anforderungen prüfen.
