# Projektagent: Telegram2Mqtt

Dieses Projekt entwickelt und betreibt eine lokale, mehrmandantenfähige Telegram–MQTT-Brücke. Lies vor Änderungen den tatsächlichen Projektstand; das Repository enthält anfangs nur die Planung. Behaupte nicht, dass geplante Funktionen bereits implementiert oder bereitgestellt sind.

## Pflegepflicht

Halte diese Datei und die projektspezifischen Skills aktuell: Aktualisiere bei Änderungen an Anforderungen, Architektur, MQTT-Vertrag, Sicherheitsmodell, Installation oder Betrieb die betroffenen Anweisungen im selben Arbeitsschritt. Entferne überholte Aussagen und kennzeichne offene Entscheidungen und noch nicht implementierte Funktionen. Dokumentiere tatsächliche Schnittstellen und Abläufe anhand des Codes, statt unbelegte Annahmen als Fakten einzutragen. Prüfe vor der Arbeit, ob Dokumentation und Implementierung übereinstimmen.

## Versionierung und Git

- Kümmere dich um eine nachvollziehbare Projektversionierung. Verwende für die Anwendung semantische Versionen (`MAJOR.MINOR.PATCH`); solange noch keine Anwendung und keine maßgebliche Versionsdatei existieren, ist keine Projektversion festgelegt. Lege die maßgebliche Versionsquelle bei ihrer Einführung fest und dokumentiere sie hier.
- Passe bei jeder Änderung der Projektversion alle tatsächlich vorhandenen maßgeblichen Versionsangaben und diese Agentenanweisungen an; dokumentiere dabei die aktuelle Version und gegebenenfalls geänderte Abläufe. Halte außerdem betroffene projektspezifische Skills aktuell.
- Führe bei jeder Änderung der Projektversion nach passenden Prüfungen automatisch einen Commit der zugehörigen Änderungen aus und pushe ihn auf den zugehörigen Remote-Branch. Prüfe vorher den Git-Status und nimm keine fremden oder geheimen Dateien unbeabsichtigt in den Commit auf. Schlägt ein Test, Commit oder Push fehl oder ist das Ziel unklar, melde den Zustand und die Ursache; erzwinge keinen Push und erfinde keinen erfolgreichen Abschluss.

## Vereinbarter Umfang

- Eine eigenständige App läuft in einem Proxmox-LXC, verbindet mehrere separat verwaltete Telegram-Bots mit einem lokalen MQTT-Broker und dient Anwendungen als Kommunikations-Backend.
- Textnachrichten fließen in beide Richtungen. Die Anwendungslogik bleibt in den angeschlossenen Apps. Direkte Gerätesteuerung, Medien und weitergehende Telegram-Funktionen gehören vorerst nicht zum vereinbarten Umfang.
- Bots werden über eine minimale, passwortgeschützte Weboberfläche im lokalen Netz verwaltet. Pro Bot werden Token und erlaubte Chat-IDs konfiguriert. Nur freigegebene Chats dürfen Nachrichten senden und empfangen. Abgelehnte Kontakte sollen sichtbar sein und freigegeben werden können; unbekannte Eingänge dürfen nicht an MQTT weitergeleitet werden.
- Ausgehende Aufträge werden persistent lokal gespeichert, bei Verbindungsproblemen erneut versucht und mit zuordenbarem Ergebnis gemeldet. Bei ungewissem Telegram-Sendeergebnis sind Duplikate möglich; keine unbegründete Exactly-once-Garantie machen.
- Die Oberfläche zeigt Verbindungszustände, Ereignisse und Fehler. Zugangsdaten dürfen nicht angezeigt oder protokolliert werden. Befehlszuordnungen müssen nicht über die Oberfläche editierbar sein.
- Home Assistant soll später über eine eigene Integration angebunden werden, die benötigte bisherige Telegram-Funktionen auf diese Brücke abbildet. Die App soll auch anderen Anwendungen dienen. Die spätere Kompatibilität nicht als bereits implementiert darstellen.

## Vorgeschlagene Architektur – noch festzulegen

- Pro Bot ein MQTT-Namensraum, etwa `telegram2mqtt/<bot-id>/event/message`, `command/send`, `event/result` und `status`. Dies sind Vorschläge, noch kein verbindlicher oder implementierter Vertrag. Vor Integration JSON-Schemas, Versionierung, Korrelation, Berechtigungen, QoS, Retain-Verhalten und Fehlerfälle festlegen und dokumentieren.
- Ein Dienst mit automatischem Start, Wiederverbindung und persistenter Warteschlange; Debian-LXC und systemd sind der vorgeschlagene Ausgangspunkt. Technologie, Datenhaltung, Netzwerk- und Betriebsdetails anhand der Anforderungen wählen.
- Für Telegram-Empfang zunächst einen separaten Test-Bot verwenden. Einen bestehenden, von Home Assistant genutzten Bot erst bei geplanter Migration übernehmen; Polling und Webhook sind nicht gleichzeitig nutzbar. Keine bestehende Integration unbeabsichtigt umstellen.
- Telegram benötigt Internetzugang; Broker und Oberfläche sind lokal. Broker-Zugang, TLS, Oberfläche und Schutz gespeicherter Geheimnisse entsprechend der tatsächlichen Umgebung konfigurieren.

## Projektskills

Diese Skills liegen bewusst im Repository und sind über diese Verweise nutzbar; automatische Skill-Erkennung hängt von der jeweiligen Agentenlaufzeit ab. Lies den passenden Skill vor der jeweiligen Aufgabe:

- [Bridge entwickeln](skills/telegram-mqtt-bridge/SKILL.md): Protokoll, Telegram-/MQTT-Verarbeitung und Tests.
- [Betrieb und Proxmox](skills/telegram-mqtt-operations/SKILL.md): Installation, Konfiguration, Betrieb und Diagnose.

## Offene Informationen

Auf Proxmox `192.168.184.2`, Node `pve`, wurde der unprivilegierte Debian-13-LXC `telegram2mqtt` (VM-ID 104) angelegt. Er nutzt `local-lvm`, `vmbr0`, DHCP und automatischen Start. Die per DHCP vergebene Adresse war bei Einrichtung `192.168.184.85` und kann sich ändern. SSH-Zugriff als `root` mit dem Schlüssel `.secret/telegram2mqtt-ssh-ed25519` und der Hostschlüsseldatei `.secret/ssh-known-hosts` wurde geprüft. Root-Passwortanmeldung über SSH ist deaktiviert. Das ursprünglich erzeugte Passwort in `.secret/telegram2mqtt-lxc-root-password.txt` wurde offengelegt und darf nicht mehr verwendet werden; ob es im Container ersetzt wurde, ist nicht bestätigt. `.secret` ist von Git ausgeschlossen. Die Anwendung ist noch nicht installiert oder implementiert.

Konkrete Broker-Einstellungen und Zugangsdaten für die spätere Anwendung sind noch nicht bekannt. Keine Tokens oder Passwörter ins Repository, in Logs oder in Beispiele mit echten Werten schreiben. Externe Infrastruktur nur im Rahmen der konkreten Beauftragung und verfügbaren Zugriffsrechte verändern.
