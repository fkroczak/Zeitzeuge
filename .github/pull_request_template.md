## Was ändert sich?

<!-- Kurz: was und warum -->

## Bedienbarkeit (bei Änderungen an der Oberfläche)

Automatische Prüfungen laufen in CI (`tests/ui_audit_test.py`). Von Hand prüfen:

- [ ] Nur mit Tastatur bedienbar (Tab, Enter, Esc, Tastenkürzel), Fokus immer sichtbar
- [ ] Mit Windows-Sprachausgabe (Narrator) oder NVDA verständlich
- [ ] Bei 150 % und 200 % Windows-Anzeige sowie im schmalen Fenster nutzbar
- [ ] Beschriftung steht direkt beim eigenen Feld, Fehler stehen als Text neben dem Feld
- [ ] Nicht mehr Auswahlmöglichkeiten gleichzeitig als nötig (Hick), Menügruppen ≤ 5 Einträge
- [ ] Texte kurz, in Du-Form, Knöpfe sagen, was sie tun
- [ ] Helles und dunkles Design geprüft
- [ ] Siehe `docs/quality-guardrails.md`
