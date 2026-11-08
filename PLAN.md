# Umsetzungsplanung Telegram2Mqtt

Stand: Planungsentwurf; der aktuelle Implementierungsstand steht am Ende dieses Dokuments. Die bestehenden Anforderungen und der tatsächliche Infrastrukturstand stehen in [AGENTS.md](AGENTS.md). Der Entwurf ist vor der Integration zu überprüfen; insbesondere sind MQTT-Vertrag, Sicherheitsmodell und Broker-Konfiguration noch nicht verbindlich.

## Ziel und Grenzen

Ein Dienst im vorhandenen Debian-13-LXC verbindet mehrere voneinander getrennt verwaltete Telegram-Bots mit einem lokalen MQTT-Broker. Er vermittelt ausschließlich Textnachrichten. Eine lokale, passwortgeschützte Oberfläche verwaltet Bots und Chat-Freigaben und zeigt Betriebszustände und Fehler. Fachlogik verbleibt bei den angeschlossenen Anwendungen. Medien, Gerätesteuerung und die spätere Home-Assistant-Integration sind nicht Teil der ersten Umsetzung.

## Technischer Entwurf

- Ein einzelner Dienst mit Python, asynchroner Verarbeitung, Weboberfläche und SQLite als lokaler Datenbank ist der vorgeschlagene Ausgangspunkt. Telegram-Empfang erfolgt je Bot über Long Polling; MQTT-Verbindung, Telegram-Worker, Warteschlange und Oberfläche laufen unter einem Prozessmanager. Bibliotheken und konkrete Versionen werden vor Implementierung nach Wartbarkeit und Debian-13-Kompatibilität ausgewählt.
- Persistiert werden Bot-Konfiguration, Freigaben, Metadaten abgelehnter Kontakte, Empfangspositionen, Sendeaufträge und deren Zustände. SQLite-Transaktionen und ein einzelner aktiver Dienst verhindern konkurrierende Bearbeitung; Änderungen an Bots starten nur den zugehörigen Worker neu.
- Bot-IDs sind stabile, lokal vergebene Kennungen und keine Tokens. Pro Bot existieren eigene Freigaben und Topics. Jeder eingehende Text wird vor einer Veröffentlichung geprüft; unbekannte Kontakte werden mit minimalen Metadaten für die Freigabe erfasst, ihre Nachrichtentexte nicht an MQTT weitergegeben. Vor jedem Sendeversuch wird die aktuelle Freigabe erneut geprüft.
- Telegram-Updates sollen erst nach persistenter Verarbeitung beziehungsweise Übergabe an eine persistente MQTT-Ausgangswarteschlange bestätigt werden. Auch Ergebnisse von Sendeaufträgen werden bis zur bestätigten MQTT-Veröffentlichung gespeichert. Wiederholungen können MQTT-Duplikate erzeugen; Verbraucher müssen stabile Ereignis- und Auftragskennungen zur Deduplizierung verwenden. Aufbewahrung und Begrenzungen sind vor Umsetzung festzulegen.
- Eingehende MQTT-Aufträge werden validiert und vor ihrer Bestätigung dauerhaft gespeichert. Dieselbe Auftrags-ID pro Bot darf bei identischem Inhalt keinen zweiten Auftrag erzeugen; bei abweichendem Inhalt wird ein Konflikt gemeldet. Nach einem Absturz während eines Telegram-Sendeversuchs ist das Ergebnis ungewiss: erneute Versuche können doppelte Telegram-Nachrichten erzeugen. Endzustände und Fehler werden korrelierbar veröffentlicht.

## MQTT-Vertrag: Vorschlag zur Abstimmung

Basis `telegram2mqtt/v1/<bot-id>/`; `<bot-id>` ist ein einzelnes eingeschränktes Topic-Segment. UTF-8-JSON, keine Geheimnisse in Topics oder Nutzdaten. Chat-IDs als dezimale Strings behandeln, damit große oder negative IDs unverändert bleiben. Die konkrete maximale Nutzlast und Textlänge müssen vor Implementierung festgelegt und geprüft werden.

| Topic | Richtung | Vorschlag | Retain |
| --- | --- | --- | --- |
| `event/message` | Bridge → Anwendung | `event_id`, `chat_id`, `text`, `timestamp` | nein |
| `command/send` | Anwendung → Bridge | `request_id`, `chat_id`, `text` | nein |
| `event/result` | Bridge → Anwendung | `request_id`, `status`, gegebenenfalls `error_code` und `message_id` | nein |
| `status` | Bridge → Anwendung | Verbindungsstatus und Zeitpunkt | ja |

Beispiel für einen Auftrag: `{"request_id":"example-001","chat_id":"123456789","text":"Hallo"}`. Beispiel für ein Ergebnis: `{"request_id":"example-001","status":"sent","message_id":"42"}`. Beispiele enthalten Platzhalter und keine Zugangsdaten.

Vorgesehen sind QoS 1, eine dauerhafte MQTT-Sitzung und Last Will für Offline-Status. Der Client darf eine Zustellung erst nach dauerhafter Speicherung bestätigen; die gewählte MQTT-Bibliothek muss diese Steuerung unterstützen. QoS 1 garantiert weder Telegram-Zustellung noch Duplikatfreiheit. Retain-Aufträge sollen abgelehnt werden; die zuverlässige Erkennung auch bei aktiver Subscription erfordert eine geeignete MQTT-Version und Subscription-Option und ist bei der Vertragsfestlegung zu prüfen; eine Wiederholung derselben Auftrags-ID ist idempotent zu behandeln. Für ungültiges JSON oder fehlende Auftrags-ID ist eine korrelierbare Antwort nicht immer möglich: solche Nachrichten werden verworfen und ohne Nutzlast protokolliert. Bei gültiger Auftrags-ID sind unter anderem `invalid_request`, `chat_not_allowed`, `request_id_conflict` und `delivery_failed` als Fehlercodes vorgesehen. Annahme-, Retry- und Endzustände, Grenzen für Wiederholungen und genaue JSON-Schemas bleiben vor Integration festzulegen. MQTT-Berechtigungen sollen pro Anwendung nur die benötigten Bot-Topics erlauben; die Bridge benötigt entsprechende Lese- und Schreibrechte.

## Sicherheit und Betrieb

- Webzugriff auf das lokale Netz beschränken, starke Passwörter als langsame gesalzene Hashes speichern, Sitzungen schützen und zustandsändernde Anfragen gegen CSRF absichern. TLS beziehungsweise ein vertrauenswürdiger Reverse Proxy ist abhängig vom tatsächlichen Netz festzulegen. Keine Zugangsdaten nach Speicherung wieder anzeigen.
- Bot-Tokens und Broker-Zugangsdaten werden für den Betrieb benötigt und müssen deshalb reversibel geschützt sein: separater Dienstbenutzer, restriktive Dateirechte und Schutz von Backups; Verschlüsselung und Schlüsselverwaltung abhängig vom Bedrohungsmodell festlegen. Keine Tokens, Passwörter oder vollständigen Telegram-API-URLs in Logs ausgeben. Nachrichteninhalte möglichst nicht protokollieren.
- systemd startet den Dienst automatisch neu; persistente Daten liegen außerhalb des Programmverzeichnisses. Installation, Updates, Sicherung und Wiederherstellung werden anhand der tatsächlichen Implementierung dokumentiert und getestet. Backups enthalten sensible Daten und sind entsprechend zu schützen.
- Für Entwicklung und Integration ausschließlich einen separaten Test-Bot nutzen. Ein Wechsel des bestehenden Home-Assistant-Bots erfordert einen gesonderten Migrationsplan. Der Zustand des früher offengelegten LXC-Root-Passworts ist offen und vor produktivem Betrieb zu klären; das alte Passwort darf nicht verwendet werden.

## Umsetzung und Abnahme

1. **Vertrag und Entscheidungen:** Broker-Version und Zugang, Netzgrenzen, Betriebsnutzer, Schutz der Geheimnisse, vollständige JSON-Schemas, Zustandsmodell, Wiederholungs- und Aufbewahrungsregeln festlegen. Bibliotheken auf manuelle MQTT-Bestätigung und dauerhafte Sitzungen prüfen.
2. **Grundgerüst:** Projektstruktur, maßgebliche semantische Versionsquelle, Konfiguration, Datenbankschema und Migrationen, strukturierte geheimnisfreie Logs sowie lokale Entwicklungs- und Testumgebung einrichten.
3. **Bridge-Kern:** getrennte Bot-Worker, Chat-Freigaben und abgelehnte Kontakte; MQTT-Vertrag und persistente Ein- und Ausgangsverarbeitung samt Wiederanlauf implementieren. Externe Dienste in automatisierten Tests kontrolliert ersetzen.
4. **Oberfläche:** Anmeldung, Bot-Verwaltung, Freigabe und Entzug, Status und verständliche Fehler implementieren. Gespeicherte Geheimnisse dürfen nicht erneut ausgegeben werden.
5. **Betrieb:** systemd-Einrichtung und reproduzierbare Installation für Debian 13 erstellen; Backup, Wiederherstellung und Updates erproben. Deployment in den LXC erst im konkret beauftragten Umfang und mit den erforderlichen Zugangsdaten durchführen.
6. **End-to-End-Abnahme:** Mit separatem Test-Bot und lokalem Broker erlaubte und nicht erlaubte Chats, mehrere Bots, beide Nachrichtenrichtungen, Korrelation und Fehler überprüfen. Broker- und Telegram-Ausfälle, Neustarts vor und während des Sendens, doppelte MQTT-Aufträge und den Entzug von Chat-Freigaben prüfen. Bei ungewissem Telegram-Ergebnis mögliche Duplikate ausdrücklich dokumentieren. Sicherheits- und Logprüfung sowie Backup-Wiederherstellung abschließen.

## Noch benötigte Angaben

- Broker-Adresse, Port, MQTT-Version, Authentifizierung, TLS und verfügbare ACL-Verwaltung.
- Erreichbarkeit und Netzschutz der Oberfläche, gewünschte TLS-Terminierung und Verfahren für das erste Administratorpasswort.
- Test-Bot und mindestens eine Test-Chat-ID; keine echten Zugangsdaten im Repository ablegen.
- Gewünschte Aufbewahrungsdauer, Speichergrenzen und Umgang mit dauerhaft fehlgeschlagenen Aufträgen; erwartete Last und Verfügbarkeitsanforderungen.
- Entscheidung zu Backups, Schutz gespeicherter Geheimnisse und Verantwortung für Schlüsselverwaltung. Home-Assistant-Migration bleibt ein eigener späterer Auftrag.

## Aktueller Fortschritt

Der SQLite-Kern und die HTTPS-Konfigurationsoberfläche sind vorhanden; letztere ist im LXC installiert. Broker-Zugangsdaten und Bot-Tokens können dort gespeichert werden. Telegram- und MQTT-Netzwerkadapter fehlen; der Entwurf oben ist weiterhin kein implementierter MQTT-Vertrag. Betrieb und Erstzugang stehen in BETRIEB.md.
